"""Ed25519 signing for firewall certificates and canonical hashing for intents.

A certificate is signed over the canonical JSON of all its fields except the
signature and public key. Verification recomputes that canonical payload, so any
post-issue mutation invalidates the signature — anyone can confirm *integrity*
offline with the embedded public key, no call back to the arena required.

*Authenticity* (that the real arena signed it, not a forger who self-signed with
their own keypair) requires pinning: compare the certificate's public key against
the arena's published issuer key. ``verify_certificate(cert, expected_public_key_hex=...)``
does this; the published key lives in ``config/issuer_pubkey.hex`` and at ``GET /pubkey``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..domain.verdict import Certificate

_SIG_FIELDS = {"signature_hex", "public_key_hex"}


def canonical_json(data: dict[str, Any]) -> bytes:
    """Deterministic JSON bytes for signing: sorted keys, no whitespace. Numeric fields are
    plain JSON numbers — a cross-language verifier should parse them as IEEE-754 doubles to
    reproduce the digest. Certificates and ledger records never carry non-finite values by
    construction (the firewall rejects a non-finite size before issuing a verdict)."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _model_canonical(model: Any, exclude: frozenset[str] = frozenset()) -> bytes:
    data = model.model_dump(mode="json")
    for key in exclude:
        data.pop(key, None)
    return canonical_json(data)


def model_canonical(model: Any, exclude: frozenset[str] = frozenset()) -> bytes:
    """Public canonical-bytes helper for any pydantic model (sorted keys, no ws)."""
    return _model_canonical(model, exclude)


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def intent_hash(intent: Any) -> str:
    """Stable sha256 over the canonical form of a :class:`TradeIntent`."""
    return sha256_hex(_model_canonical(intent))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_nonce() -> str:
    """A short, URL-safe random nonce (96 bits) so identical intents sign distinctly."""
    return base64.urlsafe_b64encode(os.urandom(12)).decode("ascii").rstrip("=")


class Signer:
    """Wraps an Ed25519 private key and signs certificates."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._sk = private_key
        self._pk = private_key.public_key()

    @property
    def public_key_hex(self) -> str:
        raw = self._pk.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return raw.hex()

    @property
    def fingerprint(self) -> str:
        """Short, stable issuer id: first 16 hex chars of sha256(public key)."""
        return sha256_hex(bytes.fromhex(self.public_key_hex))[:16]

    def sign_certificate(self, cert: Certificate) -> Certificate:
        """Return a copy of ``cert`` with issuer, signature, and public key set."""
        unsigned = cert.model_copy(
            update={"issuer": self.fingerprint, "signature_hex": "", "public_key_hex": ""}
        )
        payload = _model_canonical(unsigned, exclude=frozenset(_SIG_FIELDS))
        signature = self._sk.sign(payload)
        return unsigned.model_copy(
            update={"signature_hex": signature.hex(), "public_key_hex": self.public_key_hex}
        )

    def sign_bytes(self, payload: bytes) -> str:
        """Sign arbitrary bytes (used by the ledger), returning a hex signature."""
        return self._sk.sign(payload).hex()

    @classmethod
    def generate(cls) -> "Signer":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_pem_b64(cls, b64: str) -> "Signer":
        """Load a signer from a base64-encoded PEM private key (for env-injected keys)."""
        key = serialization.load_pem_private_key(base64.b64decode(b64), password=None)
        if not isinstance(key, Ed25519PrivateKey):  # pragma: no cover - defensive
            raise TypeError("ARENA_SIGNING_KEY_B64 is not an Ed25519 key")
        return cls(key)

    @classmethod
    def load_or_create(cls, path: Path | str) -> "Signer":
        """Load a PEM private key from ``path``, or generate and persist one."""
        path = Path(path)
        if path.exists():
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
            if not isinstance(key, Ed25519PrivateKey):  # pragma: no cover - defensive
                raise TypeError("signing key is not Ed25519")
            return cls(key)
        sk = Ed25519PrivateKey.generate()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            pem = sk.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            path.write_bytes(pem)
            try:  # best-effort restrictive perms (no-op on some platforms)
                os.chmod(path, 0o600)
            except OSError:  # pragma: no cover
                pass
        except OSError:
            # read-only filesystem (e.g. serverless): use an ephemeral in-memory key
            # rather than crashing. Certs stay self-verifying; set ARENA_SIGNING_KEY_B64
            # for a stable issuer in such deployments.
            pass
        return cls(sk)


def build_signer(b64: str | None, path: Path | str) -> Signer:
    """Prefer an env-injected base64 PEM key; otherwise load/create one at ``path``."""
    if b64:
        return Signer.from_pem_b64(b64)
    return Signer.load_or_create(path)


def verify_certificate(cert: Certificate, expected_public_key_hex: str | None = None) -> bool:
    """Verify a certificate's Ed25519 signature against its embedded public key.

    Integrity by default: returns ``False`` for a missing signature/key, a tampered
    payload, or any malformed field — never raises.

    Pass ``expected_public_key_hex`` (the arena's published issuer key) to ALSO require
    authenticity: that this exact issuer signed it, not a forger who self-signed with
    their own keypair. Without pinning, a self-consistent forged certificate verifies
    as ``True`` (integrity holds), which is why provenance checks must pin the key.
    """
    if not cert.signature_hex or not cert.public_key_hex:
        return False
    if expected_public_key_hex is not None and not hmac.compare_digest(
        cert.public_key_hex.strip().lower(), expected_public_key_hex.strip().lower()
    ):
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(cert.public_key_hex))
        unsigned = cert.model_copy(update={"signature_hex": "", "public_key_hex": ""})
        payload = _model_canonical(unsigned, exclude=frozenset(_SIG_FIELDS))
        public_key.verify(bytes.fromhex(cert.signature_hex), payload)
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_bytes(public_key_hex: str, signature_hex: str, payload: bytes) -> bool:
    """Verify a raw Ed25519 signature over ``payload``. Never raises."""
    if not public_key_hex or not signature_hex:
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        public_key.verify(bytes.fromhex(signature_hex), payload)
        return True
    except (InvalidSignature, ValueError):
        return False


_ENVELOPE_SIG_KEYS = ("payload_sha256", "issuer", "public_key_hex", "signature_hex")


def sign_payload(payload: dict[str, Any], signer: Signer) -> dict[str, Any]:
    """Wrap any JSON-able payload in a signed, tamper-evident envelope (arena Ed25519 key).

    Returns the payload plus ``payload_sha256``, ``issuer``, ``public_key_hex`` and
    ``signature_hex``. Used for signed artifacts beyond certificates — debate transcripts,
    trade memos — so they all verify offline the same way a certificate does.
    """
    raw = canonical_json(payload)
    return {
        **payload,
        "payload_sha256": sha256_hex(raw),
        "issuer": signer.fingerprint,
        "public_key_hex": signer.public_key_hex,
        "signature_hex": signer.sign_bytes(raw),
    }


def verify_payload(envelope: dict[str, Any], expected_public_key_hex: str | None = None) -> bool:
    """Verify a signed payload envelope. Integrity by default; pins the issuer if given. Never raises."""
    payload = {k: v for k, v in envelope.items() if k not in _ENVELOPE_SIG_KEYS}
    raw = canonical_json(payload)
    if sha256_hex(raw) != envelope.get("payload_sha256"):
        return False
    pk = envelope.get("public_key_hex", "")
    if expected_public_key_hex is not None and pk.strip().lower() != expected_public_key_hex.strip().lower():
        return False
    return verify_bytes(pk, envelope.get("signature_hex", ""), raw)
