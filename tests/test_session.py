"""US market-session classifier + the firewall's off-hours tokenized-equity gate."""

from __future__ import annotations

from datetime import datetime, timezone

from bitarena.domain.intent import TradeIntent
from bitarena.domain.mandate import default_arena_mandate
from bitarena.domain.market import InstrumentType, Quote
from bitarena.domain.session import is_market_open, us_eastern, us_equity_session
from bitarena.domain.verdict import Decision
from bitarena.firewall import Firewall
from bitarena.firewall.firewall import EvalContext


def _ms(y: int, mo: int, d: int, h: int, mi: int = 0) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


# -- session classification -------------------------------------------------

def test_regular_session_open():
    assert us_equity_session(_ms(2026, 6, 19, 18)) == "open"  # Fri 14:00 EDT
    assert is_market_open(_ms(2026, 6, 19, 18))


def test_weekend_closed():
    assert us_equity_session(_ms(2026, 6, 20, 18)) == "closed"  # Sat
    assert us_equity_session(_ms(2026, 6, 21, 18)) == "closed"  # Sun


def test_weekday_overnight_closed():
    assert us_equity_session(_ms(2026, 6, 17, 7)) == "closed"  # Wed 03:00 EDT


def test_open_close_boundaries():
    assert us_equity_session(_ms(2026, 6, 19, 13, 30)) == "open"    # 09:30 EDT exactly
    assert us_equity_session(_ms(2026, 6, 19, 13, 29)) == "closed"  # 09:29 EDT
    assert us_equity_session(_ms(2026, 6, 19, 20, 0)) == "closed"   # 16:00 EDT exactly (exclusive)
    assert us_equity_session(_ms(2026, 6, 19, 19, 59)) == "open"    # 15:59 EDT


def test_dst_transition():
    # 20:30 UTC: winter (EST -5) -> 15:30 ET open; summer (EDT -4) -> 16:30 ET closed
    assert us_equity_session(_ms(2026, 1, 15, 20, 30)) == "open"    # Thu, EST
    assert us_equity_session(_ms(2026, 6, 18, 20, 30)) == "closed"  # Thu, EDT


def test_us_eastern_offset_dst_aware():
    assert us_eastern(_ms(2026, 6, 19, 18)).hour == 14  # EDT (-4)
    assert us_eastern(_ms(2026, 1, 15, 19)).hour == 14  # EST (-5)


def test_malformed_timestamp_never_raises():
    # negative / pre-epoch timestamps must not throw out of the fail-closed gate (Windows OSError)
    for bad in (-1_000, 0, -86_400_000):
        assert us_equity_session(bad) in ("open", "closed")


# -- firewall session gate --------------------------------------------------

def _harness():
    fw = Firewall()
    m = default_arena_mandate(10_000.0, allowed_symbols=("RAAPLUSDT",))  # order cap 2000; off-hrs 1000

    def ctx(t: int, man=m, sym: str = "RAAPLUSDT") -> EvalContext:
        q = Quote(symbol=sym, bid=100.0, ask=100.1, last=100.0, ts=t)
        return EvalContext(mandate=man, equity_usd=10_000.0, quote=q, now_ms=t, max_quote_age_ms=10**15)

    def it(n: float, sym: str = "RAAPLUSDT", inst: InstrumentType = InstrumentType.TOKENIZED_EQUITY):
        return TradeIntent(agent_id="t", symbol=sym, side="buy", notional_usd=n, instrument=inst)

    return fw, ctx, it


def test_off_hours_tokenized_equity_is_capped():
    fw, ctx, it = _harness()
    v = fw.evaluate(it(1500.0), ctx(_ms(2026, 6, 20, 18)))  # Sat -> closed
    assert v.decision is Decision.ALLOW_CAPPED
    assert abs((v.effective_notional_usd or 0) - 1000.0) < 1e-6  # 2000 * 0.5
    assert any(g.gate == "session" for g in v.gates)


def test_in_session_tokenized_equity_not_capped():
    fw, ctx, it = _harness()
    v = fw.evaluate(it(1500.0), ctx(_ms(2026, 6, 19, 18)))  # Fri 14:00 -> open
    assert v.decision is Decision.ALLOW
    assert abs((v.effective_notional_usd or 0) - 1500.0) < 1e-6
    assert not any(g.gate == "session" for g in v.gates)


def test_perp_unaffected_off_hours():
    fw, ctx, it = _harness()
    mp = default_arena_mandate(10_000.0, allowed_symbols=("BTCUSDT",))
    v = fw.evaluate(it(1500.0, "BTCUSDT", InstrumentType.PERP), ctx(_ms(2026, 6, 20, 18), mp, "BTCUSDT"))
    assert v.decision is Decision.ALLOW
    assert not any(g.gate == "session" for g in v.gates)


def test_off_hours_gate_never_opens_headroom():
    # the session gate only tightens: an oversized off-hours order is capped BELOW the normal cap
    fw, ctx, it = _harness()
    v = fw.evaluate(it(50_000.0), ctx(_ms(2026, 6, 20, 18)))
    assert v.decision is Decision.ALLOW_CAPPED
    assert (v.effective_notional_usd or 0) <= 1000.0 + 1e-6
