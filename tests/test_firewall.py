"""Tests for the firewall evaluate engine: ALLOW / ALLOW_CAPPED / REJECT + certs."""

from __future__ import annotations

from bitarena.domain import (
    Decision,
    InstrumentType,
    Quote,
    Side,
    TradeIntent,
    UniverseConstraint,
    default_arena_mandate,
)
from bitarena.firewall import EvalContext, Firewall, verify_certificate


def _quote(mid=100.0, ts=1_000) -> Quote:
    return Quote(symbol="BTCUSDT", bid=mid - 0.05, ask=mid + 0.05, last=mid, ts=ts)


def _ctx(**kw) -> EvalContext:
    base = dict(
        mandate=default_arena_mandate(10_000),  # order cap 2000, exposure 30000, lev 3
        equity_usd=10_000.0,
        quote=_quote(),
        current_exposure_usd=0.0,
        daily_count=0,
        halted=False,
        now_ms=1_000,
        max_quote_age_ms=60_000,
    )
    base.update(kw)
    return EvalContext(**base)


def _intent(**kw) -> TradeIntent:
    base = dict(agent_id="swarm", symbol="BTCUSDT", side=Side.BUY, notional_usd=50.0)
    base.update(kw)
    return TradeIntent(**base)


def test_allow_within_limits_and_signed_cert():
    fw = Firewall.with_key("./.keys/test_arena.pem")
    v = fw.evaluate(_intent(notional_usd=50.0), _ctx())
    assert v.decision is Decision.ALLOW
    assert v.allowed and v.effective_notional_usd == 50.0
    assert v.certificate is not None and verify_certificate(v.certificate) is True


def test_reject_excluded_symbol():
    m = default_arena_mandate(10_000).model_copy(
        update={"universe": UniverseConstraint(exclude_symbols=("BTCUSDT",))}
    )
    v = Firewall().evaluate(_intent(), _ctx(mandate=m))
    assert v.decision is Decision.REJECT
    assert v.first_failure.gate == "universe"


def test_reject_disallowed_instrument():
    caps = default_arena_mandate(10_000).hard_caps.model_copy(
        update={"allowed_instruments": (InstrumentType.SPOT,)}
    )
    m = default_arena_mandate(10_000).model_copy(update={"hard_caps": caps})
    v = Firewall().evaluate(_intent(instrument=InstrumentType.PERP), _ctx(mandate=m))
    assert v.decision is Decision.REJECT
    assert v.first_failure.gate == "instrument"


def test_reject_no_quote_fail_closed():
    v = Firewall().evaluate(_intent(), _ctx(quote=None))
    assert v.decision is Decision.REJECT
    assert v.first_failure.gate == "quote"


def test_reject_stale_quote():
    v = Firewall().evaluate(_intent(), _ctx(quote=_quote(ts=0), now_ms=10_000_000))
    assert v.decision is Decision.REJECT
    assert v.first_failure.gate == "quote"


def test_reject_daily_count_exhausted():
    # default arena mandate allows 200 trades/day
    v = Firewall().evaluate(_intent(), _ctx(daily_count=200))
    assert v.decision is Decision.REJECT
    assert v.first_failure.gate == "daily_count"


def test_allow_capped_over_order_notional():
    # order cap is 2000; request 5000 -> capped to 2000 (exposure/leverage have room)
    v = Firewall().evaluate(_intent(notional_usd=5_000.0), _ctx())
    assert v.decision is Decision.ALLOW_CAPPED
    assert v.effective_notional_usd == 2_000.0


def test_allow_capped_by_exposure_room():
    # exposure cap 30000, already 29500 used, order cap 2000 -> headroom only 500
    v = Firewall().evaluate(_intent(notional_usd=2_000.0), _ctx(current_exposure_usd=29_500.0))
    assert v.decision is Decision.ALLOW_CAPPED
    assert v.effective_notional_usd == 500.0


def test_reject_when_no_headroom():
    # exposure fully used -> allowable 0 -> REJECT
    v = Firewall().evaluate(_intent(notional_usd=2_000.0), _ctx(current_exposure_usd=30_000.0))
    assert v.decision is Decision.REJECT


def test_quantity_priced_via_quote():
    # quantity 30 @ mid 100 = 3000 notional -> exceeds order cap 2000 -> capped
    v = Firewall().evaluate(_intent(notional_usd=None, quantity=30.0), _ctx(quote=_quote(mid=100.0)))
    assert v.decision is Decision.ALLOW_CAPPED
    assert v.effective_notional_usd == 2_000.0


def test_reduce_only_without_a_position_is_not_exempt():
    # A1: a reduce_only flag on a fresh order (no opposing position) must NOT bypass the
    # exposure cap. With exposure at the cap there is no room -> REJECT (the bypass is fixed).
    v = Firewall().evaluate(
        _intent(side=Side.BUY, notional_usd=500.0, reduce_only=True),
        _ctx(current_exposure_usd=30_000.0, position_qty=0.0),
    )
    assert v.decision is Decision.REJECT


def test_genuine_reduction_is_exempt_from_exposure_cap():
    # A real reduction (SELL opposing a long, within the position size) is exempt from the
    # exposure/leverage caps and allowed up to the order cap even with exposure at the cap.
    long_qty = 30_000.0 / _quote().mid  # a long position worth ~$30k
    v = Firewall().evaluate(
        _intent(side=Side.SELL, notional_usd=500.0, reduce_only=True),
        _ctx(current_exposure_usd=30_000.0, position_qty=long_qty),
    )
    assert v.decision is Decision.ALLOW
    assert v.effective_notional_usd == 500.0


def test_halt_blocks_everything():
    v = Firewall().evaluate(_intent(), _ctx(halted=True))
    assert v.decision is Decision.REJECT
    assert v.first_failure.gate == "halt"


def test_signed_verdict_latency_under_budget():
    # a full signed verdict (all gates + Ed25519) is sub-millisecond; 5ms is a very
    # generous regression guard that still catches a catastrophic slowdown.
    import time

    fw = Firewall()
    intent, ctx = _intent(), _ctx()
    for _ in range(50):  # warmup
        fw.evaluate(intent, ctx)
    t0 = time.perf_counter()
    for _ in range(300):
        fw.evaluate(intent, ctx)
    mean_ms = (time.perf_counter() - t0) / 300 * 1_000.0
    assert mean_ms < 5.0
