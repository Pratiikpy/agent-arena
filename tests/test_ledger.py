"""Tests for the signed, hash-chained trade ledger and tamper detection."""

from __future__ import annotations

from bitarena.domain.market import Side
from bitarena.domain.verdict import Decision
from bitarena.firewall.signing import Signer
from bitarena.ledger.ledger import SignedLedger


def _append(ledger: SignedLedger, seq_price: float, bal_before: float, bal_after: float):
    return ledger.append(
        ts=1_700_000_000_000 + len(ledger),
        agent_id="swarm",
        symbol="BTCUSDT",
        side=Side.BUY,
        price=seq_price,
        quantity=0.01,
        notional_usd=seq_price * 0.01,
        fee_usd=0.06,
        balance_before_usd=bal_before,
        balance_after_usd=bal_after,
        decision=Decision.ALLOW,
        cert_hash="deadbeef",
    )


def test_append_and_verify_clean_chain():
    led = SignedLedger(Signer.generate())
    _append(led, 60_000, 10_000, 9_400)
    _append(led, 61_000, 9_400, 8_790)
    ok, issues = led.verify()
    assert ok and issues == []
    assert len(led) == 2
    assert led.records[1].prev_hash == led.records[0].record_hash


def test_required_fields_present():
    led = SignedLedger(Signer.generate())
    r = _append(led, 60_000, 10_000, 9_400)
    rows = led.required_fields_rows()
    assert set(rows[0]) >= {"timestamp_ms", "pair", "direction", "price", "quantity", "balance_change_usd"}
    assert rows[0]["pair"] == "BTCUSDT" and rows[0]["direction"] == "buy"
    assert abs(r.balance_change_usd - (-600.0)) < 1e-9


def test_tamper_mutate_quantity_detected():
    led = SignedLedger(Signer.generate())
    _append(led, 60_000, 10_000, 9_400)
    _append(led, 61_000, 9_400, 8_790)
    led._records[0] = led._records[0].model_copy(update={"quantity": 99.0})
    ok, issues = led.verify()
    assert not ok and any("hash mismatch" in i for i in issues)


def test_tamper_reorder_detected():
    led = SignedLedger(Signer.generate())
    _append(led, 60_000, 10_000, 9_400)
    _append(led, 61_000, 9_400, 8_790)
    led._records.reverse()
    ok, issues = led.verify()
    assert not ok


def test_tamper_delete_detected():
    led = SignedLedger(Signer.generate())
    _append(led, 60_000, 10_000, 9_400)
    _append(led, 61_000, 9_400, 8_790)
    _append(led, 62_000, 8_790, 8_180)
    del led._records[1]
    ok, issues = led.verify()
    assert not ok


def test_persistence_roundtrip_and_csv(tmp_path):
    path = tmp_path / "ledger.jsonl"
    signer = Signer.generate()
    led = SignedLedger(signer, path)
    _append(led, 60_000, 10_000, 9_400)
    _append(led, 61_000, 9_400, 8_790)

    reloaded = SignedLedger(signer, path)  # load from disk
    ok, _ = reloaded.verify()
    assert ok and len(reloaded) == 2

    csv_path = tmp_path / "trades.csv"
    reloaded.write_csv(csv_path)
    text = csv_path.read_text(encoding="utf-8")
    assert "pair" in text and "BTCUSDT" in text
