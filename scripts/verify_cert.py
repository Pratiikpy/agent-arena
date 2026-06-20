"""Independently verify an Agent Arena certificate — fully offline, no server.

A certificate embeds its own Ed25519 public key and signature, so anyone can verify its
*integrity* (not tampered) with nothing but this script. To also confirm *authenticity*
(that Agent Arena signed it, not a forger who self-signed with their own keypair), pin the
issuer key with --issuer-key. This is the "don't trust us, verify it yourself" tool.

    # integrity only (from a file or piped)
    uv run python scripts/verify_cert.py --file cert.json
    cat verdict.json | uv run python scripts/verify_cert.py
    # integrity + authenticity (pin against the published issuer key)
    uv run python scripts/verify_cert.py --file cert.json --issuer-key config/issuer_pubkey.hex

Accepts either a bare certificate object or a full firewall verdict (it pulls the
`certificate` field out). --issuer-key accepts a path to a hex pubkey file or the hex itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from bitarena.domain import Certificate
from bitarena.firewall import verify_certificate

# Make output encoding-independent: on a default Windows console (cp1252) the ✓/✗ marks
# printed below would otherwise raise UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover - unusual stdio objects without reconfigure
        pass


def _resolve_issuer_key(value: str | None) -> str | None:
    """--issuer-key may be a path to a hex file or the hex string itself."""
    if not value:
        return None
    if os.path.exists(value):
        return open(value, encoding="utf-8").read().strip()
    return value.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an Agent Arena certificate offline.")
    parser.add_argument("--file", help="path to a JSON file (certificate or verdict)")
    parser.add_argument(
        "--issuer-key",
        help="pin authenticity: a hex pubkey (or path to one, e.g. config/issuer_pubkey.hex)",
    )
    args = parser.parse_args()

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError as exc:
        print(f"✗ not valid JSON: {exc}")
        return 2
    if isinstance(data, dict) and "certificate" in data and isinstance(data["certificate"], dict):
        data = data["certificate"]

    try:
        cert = Certificate(**data)
    except Exception as exc:
        print(f"✗ malformed certificate: {exc}")
        return 2

    ok = verify_certificate(cert)  # integrity
    mark = "✓" if ok else "✗"
    print(f"{mark} signature {'VALID' if ok else 'INVALID (tampered or wrong key)'}")
    print(f"  decision    : {cert.decision.value}")
    print(f"  issuer      : {cert.issuer}")
    print(f"  intent_hash : {cert.intent_hash}")
    print(f"  public_key  : {cert.public_key_hex}")

    expected = _resolve_issuer_key(args.issuer_key)
    trusted = True
    if expected is not None:
        trusted = verify_certificate(cert, expected_public_key_hex=expected)
        tmark = "✓" if trusted else "✗"
        print(
            f"{tmark} issuer      : "
            + ("TRUSTED (matches pinned key)" if trusted else "UNTRUSTED (not signed by the pinned issuer)")
        )
    return 0 if (ok and trusted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
