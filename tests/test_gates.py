"""Tests for the individual pure risk gates."""

from __future__ import annotations

from bitarena.domain import (
    InstrumentType,
    Quote,
    Side,
    TradeIntent,
    UniverseConstraint,
    default_arena_mandate,
)
from bitarena.firewall import gates


def _intent(**kw) -> TradeIntent:
    base = dict(agent_id="a", symbol="BTCUSDT", side=Side.BUY, notional_usd=50.0)
    base.update(kw)
    return TradeIntent(**base)


def test_halt_gate():
    assert gates.gate_halt(False).passed is True
    assert gates.gate_halt(True).passed is False


def test_universe_exclude_and_allowlist():
    m = default_arena_mandate(10_000).model_copy(
        update={
            "universe": UniverseConstraint(
                allowed_symbols=("BTCUSDT", "ETHUSDT"), exclude_symbols=("ETHUSDT",)
            )
        }
    )
    assert gates.gate_universe(_intent(symbol="btcusdt"), m).passed is True
    assert gates.gate_universe(_intent(symbol="ethusdt"), m).passed is False  # excluded wins
    assert gates.gate_universe(_intent(symbol="solusdt"), m).passed is False  # not in allowlist


def test_instrument_gate():
    m = default_arena_mandate(10_000).model_copy(
        update={
            "hard_caps": default_arena_mandate(10_000).hard_caps.model_copy(
                update={"allowed_instruments": (InstrumentType.SPOT,)}
            )
        }
    )
    assert gates.gate_instrument(_intent(instrument=InstrumentType.SPOT), m).passed is True
    assert gates.gate_instrument(_intent(instrument=InstrumentType.PERP), m).passed is False


def test_quote_sanity():
    assert gates.gate_quote_sanity(None, None, None).passed is False
    crossed = Quote(symbol="BTCUSDT", bid=101, ask=100, last=100, ts=0)
    assert gates.gate_quote_sanity(crossed, None, None).passed is False
    fresh = Quote(symbol="BTCUSDT", bid=100, ask=100.1, last=100, ts=1_000)
    assert gates.gate_quote_sanity(fresh, 1_000, 60_000).passed is True
    stale = Quote(symbol="BTCUSDT", bid=100, ask=100.1, last=100, ts=0)
    assert gates.gate_quote_sanity(stale, 120_000, 60_000).passed is False


def test_daily_count_gate():
    m = default_arena_mandate(10_000)
    cap = m.hard_caps.max_trades_per_day
    assert gates.gate_daily_count(cap - 1, m).passed is True
    assert gates.gate_daily_count(cap, m).passed is False


def test_leverage_request_gate():
    m = default_arena_mandate(10_000, max_leverage=3.0)
    assert gates.gate_leverage_request(_intent(leverage=3.0), m).passed is True
    assert gates.gate_leverage_request(_intent(leverage=5.0), m).passed is False


def test_expiry_gate():
    base = default_arena_mandate(10_000)
    assert gates.gate_expiry(base).passed is True  # no expiry set -> passes
    future = base.model_copy(update={"expires_at": "2999-01-01T00:00:00+00:00"})
    assert gates.gate_expiry(future).passed is True
    past = base.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"})
    assert gates.gate_expiry(past).passed is False  # expired
    naive_future = base.model_copy(update={"expires_at": "2999-01-01T00:00:00"})  # no tz -> treated as UTC
    assert gates.gate_expiry(naive_future).passed is True
    bad = base.model_copy(update={"expires_at": "not-a-timestamp"})
    assert gates.gate_expiry(bad).passed is False  # unparseable -> fail-closed


def test_min_price_gate():
    m = default_arena_mandate(10_000).model_copy(
        update={"universe": UniverseConstraint(min_price_usd=10.0)}
    )
    assert gates.gate_min_price(m, 25.0).passed is True
    assert gates.gate_min_price(m, 5.0).passed is False
    assert gates.gate_min_price(m, None).passed is False  # fail-closed
