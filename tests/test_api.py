"""Tests for the FastAPI app (offline mode, no network)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from bitarena.api.app import create_app


def _client(tmp_path=None):
    return TestClient(create_app(offline=True, evidence_dir=str(tmp_path) if tmp_path else "evidence/last_run"))


def test_health():
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["issuer"]


def test_firewall_allow_signed():
    r = _client().post("/firewall", json={"symbol": "BTCUSDT", "side": "buy", "notional_usd": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] in ("ALLOW", "ALLOW_CAPPED")
    assert body["certificate_valid"] is True


def test_firewall_capped():
    r = _client().post("/firewall", json={"symbol": "BTCUSDT", "side": "buy", "notional_usd": 999999})
    assert r.json()["decision"] == "ALLOW_CAPPED"


def test_firewall_rejects_excluded_via_bad_sizing():
    # missing both notional and quantity -> 400 from intent validation
    r = _client().post("/firewall", json={"symbol": "BTCUSDT", "side": "buy"})
    assert r.status_code == 400


def test_live_endpoint_serves_live_state(tmp_path):
    import json

    (tmp_path / "live").mkdir()
    (tmp_path / "live" / "leaderboard.json").write_text(
        json.dumps({"leaderboard": [{"agent_id": "funding-carry", "rank": 1}], "new_candles": 5}),
        encoding="utf-8",
    )
    client = TestClient(create_app(offline=True, evidence_dir=str(tmp_path / "last_run")))
    r = client.get("/live")
    assert r.status_code == 200
    assert r.json()["leaderboard"][0]["agent_id"] == "funding-carry"


def test_leaderboard_404_when_absent(tmp_path):
    r = _client(tmp_path).get("/leaderboard")
    assert r.status_code == 404


def test_pubkey_exposed():
    body = _client().get("/pubkey").json()
    assert body["issuer"] and len(body["public_key_hex"]) == 64


def test_verify_roundtrip_and_tamper():
    client = _client()
    verdict = client.post("/firewall", json={"symbol": "BTCUSDT", "side": "buy", "notional_usd": 50}).json()
    cert = verdict["certificate"]

    ok = client.post("/verify", json=cert).json()
    assert ok["valid"] is True and ok["issuer"] == cert["issuer"]

    tampered = dict(cert, effective_notional_usd=1_000_000_000.0)
    bad = client.post("/verify", json=tampered).json()
    assert bad["valid"] is False


def test_verify_accepts_full_verdict_not_just_bare_cert():
    # a user can re-POST the whole /firewall response to /verify; it pulls out the
    # nested certificate (matching the verify_cert.py CLI), so the natural flow works.
    client = _client()
    verdict = client.post("/firewall", json={"symbol": "BTCUSDT", "side": "buy", "notional_usd": 50}).json()
    ok = client.post("/verify", json=verdict).json()  # full verdict, not verdict["certificate"]
    assert ok["valid"] is True and ok["issuer"] == verdict["certificate"]["issuer"]


def test_verify_malformed():
    bad = _client().post("/verify", json={"not": "a cert"}).json()
    assert bad["valid"] is False
