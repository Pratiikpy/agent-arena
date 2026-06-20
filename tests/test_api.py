"""Tests for the FastAPI app (offline mode, no network)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # API tests need the [api] extra; skip cleanly without it

from fastapi.testclient import TestClient  # noqa: E402

from bitarena.api.app import create_app  # noqa: E402


def _client(tmp_path=None):
    return TestClient(create_app(offline=True, evidence_dir=str(tmp_path) if tmp_path else "evidence/last_run"))


def test_health():
    r = _client().get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["issuer"]


def test_pulse_is_live_and_signed():
    r = _client().get("/pulse")
    assert r.status_code == 200
    body = r.json()
    assert body["server_time_ms"] > 0
    assert body["data_source"] in ("bitget-live", "synthetic")
    assert body["quote"]["mid"] and body["quote"]["mid"] > 0
    assert body["quote"]["age_ms"] is not None and body["quote"]["age_ms"] < 120_000  # fresh
    assert body["verdict"]["decision"] in ("ALLOW", "ALLOW_CAPPED", "REJECT")
    assert body["regime"] in ("NORMAL", "RISK_OFF", "FAST_RISK_OFF")
    assert body["regime"] == "NORMAL" and body["kill_switch_armed"] is False  # offline: no live crash signal
    assert body["issuer"]
    assert body["certificate"] is not None
    assert body["certificate_valid"] is True  # the heartbeat verdict is genuinely signed


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


def test_ledger_rejects_path_traversal():
    # A3: the agent param must not be able to escape the ledgers directory (CWE-22)
    client = _client()
    assert client.get("/ledger", params={"agent": "../ledgers/regime"}).status_code == 400
    assert client.get("/ledger", params={"agent": "../../SUBMISSION"}).status_code == 400
    assert client.get("/ledger", params={"agent": "..%2f..%2fpwned"}).status_code == 400


def test_verify_reports_trusted_issuer_and_catches_forgery():
    # A2: /verify distinguishes integrity (valid) from authenticity (trusted_issuer).
    from bitarena.domain.verdict import Certificate
    from bitarena.firewall.signing import Signer

    client = _client()
    cert = client.post("/firewall", json={"symbol": "BTCUSDT", "side": "buy", "notional_usd": 50}).json()["certificate"]
    good = client.post("/verify", json=cert).json()
    assert good["valid"] is True and good["trusted_issuer"] is True

    forged = Signer.generate().sign_certificate(Certificate(**cert))  # attacker self-signs
    bad = client.post("/verify", json=forged.model_dump()).json()
    assert bad["valid"] is True and bad["trusted_issuer"] is False  # integrity ok, but NOT this arena


def test_debate_endpoint_returns_a_gated_debate():
    # /debate is a judge-facing Track-1 surface (the LLM debate). Confirm it serves a
    # structured, firewall-gated debate (signals + a verdict), not an error.
    r = _client().get("/debate")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body.get("signals"), list) and body["signals"]
    assert body["verdict"]["decision"] in ("ALLOW", "ALLOW_CAPPED", "REJECT", "HOLD")
    assert body.get("rationale")


def test_root_serves_the_ui():
    r = _client().get("/")
    assert r.status_code == 200
    assert "Agent Arena" in r.text  # the production single-page UI is served at /


def test_pulse_and_firewall_live_path_with_kill_switch():
    # Exercise the PRODUCTION live path (offline tests otherwise skip it): inject a market client
    # returning a fresh quote + a crashing candle window. /pulse must report the live source and
    # ARM the kill-switch; /firewall's live quote path must still return a signed verdict.
    import time

    from bitarena.domain.market import Candle, InstrumentType, Quote

    now = int(time.time() * 1000)

    class FakeClient:
        def get_quote(self, symbol, instrument=InstrumentType.SPOT):
            return Quote(symbol=symbol, bid=99.9, ask=100.1, last=100.0, ts=now)

        def get_candles(self, symbol, instrument, limit=12, **k):
            prices = [100, 100, 100, 100, 98, 95, 92, 90, 88, 86, 84, 82]  # ~18% fast crash
            return [Candle(ts=now + i, open=p, high=p, low=p, close=p, volume=1.0)
                    for i, p in enumerate(prices)]

    c = TestClient(create_app(offline=True, market_client=FakeClient(), evidence_dir="evidence/last_run"))

    pulse = c.get("/pulse").json()
    assert pulse["data_source"] == "bitget-live"
    assert pulse["regime"] == "FAST_RISK_OFF" and pulse["kill_switch_armed"] is True
    assert pulse["certificate_valid"] is True

    fw = c.post("/firewall", json={"agent_id": "a", "symbol": "BTCUSDT", "side": "buy", "notional_usd": 50}).json()
    assert fw["decision"] in ("ALLOW", "ALLOW_CAPPED", "REJECT")
    assert fw["certificate_valid"] is True


def test_ledger_success_returns_signed_records():
    # the happy path: a real, existing agent ledger returns its records (last_run is signed)
    r = _client().get("/ledger?agent=swarm")
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "swarm" and body["count"] >= 1 and body["records"]
