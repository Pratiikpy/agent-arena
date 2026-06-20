"""Tests for Ed25519 certificate signing, verification, and tamper detection."""

from __future__ import annotations

from bitarena.domain.verdict import Certificate, Decision
from bitarena.firewall.signing import Signer, intent_hash, utc_now_iso, verify_certificate
from bitarena.domain import Side, TradeIntent


def _cert(decision=Decision.ALLOW, notional=50.0) -> Certificate:
    return Certificate(
        intent_hash="a" * 64,
        decision=decision,
        effective_notional_usd=notional,
        issued_at=utc_now_iso(),
        issuer="",
        nonce="nonce-1",
    )


def test_sign_and_verify_roundtrip():
    signer = Signer.generate()
    signed = signer.sign_certificate(_cert())
    assert signed.signature_hex and signed.public_key_hex
    assert signed.issuer == signer.fingerprint
    assert verify_certificate(signed) is True


def test_tamper_decision_fails_verification():
    signer = Signer.generate()
    signed = signer.sign_certificate(_cert(decision=Decision.REJECT))
    tampered = signed.model_copy(update={"decision": Decision.ALLOW})
    assert verify_certificate(tampered) is False


def test_tamper_notional_fails_verification():
    signer = Signer.generate()
    signed = signer.sign_certificate(_cert(notional=50.0))
    tampered = signed.model_copy(update={"effective_notional_usd": 5_000_000.0})
    assert verify_certificate(tampered) is False


def test_wrong_public_key_fails():
    signer = Signer.generate()
    other = Signer.generate()
    signed = signer.sign_certificate(_cert())
    swapped = signed.model_copy(update={"public_key_hex": other.public_key_hex})
    assert verify_certificate(swapped) is False


def test_unsigned_certificate_is_invalid():
    assert verify_certificate(_cert()) is False


def test_load_or_create_persists_key(tmp_path):
    path = tmp_path / "k" / "arena.pem"
    s1 = Signer.load_or_create(path)
    assert path.exists()
    signed = s1.sign_certificate(_cert())
    s2 = Signer.load_or_create(path)  # reload same key
    assert s2.public_key_hex == s1.public_key_hex
    assert verify_certificate(signed) is True


def test_signer_pem_b64_roundtrip():
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from bitarena.firewall.signing import build_signer

    sk = Ed25519PrivateKey.generate()
    pem = sk.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    b64 = base64.b64encode(pem).decode()
    s1 = Signer.from_pem_b64(b64)
    s2 = build_signer(b64, "unused.pem")  # b64 takes precedence over path
    assert s1.public_key_hex == s2.public_key_hex
    signed = s1.sign_certificate(_cert())
    assert verify_certificate(signed) is True


def test_intent_hash_is_stable_and_order_independent():
    a = TradeIntent(agent_id="x", symbol="BTCUSDT", side=Side.BUY, notional_usd=10)
    b = TradeIntent(side=Side.BUY, notional_usd=10, symbol="BTCUSDT", agent_id="x")
    assert intent_hash(a) == intent_hash(b)
    c = TradeIntent(agent_id="x", symbol="ETHUSDT", side=Side.BUY, notional_usd=10)
    assert intent_hash(a) != intent_hash(c)
