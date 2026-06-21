"""Property/fuzz tests — the firewall's safety invariants must hold over a large
randomized input space, not just the hand-picked cases in test_firewall.py.

For a safety-critical gate this is the difference between "we tested some cases" and
"these invariants hold across the input space." Seeded RNG -> fully deterministic.
"""

from __future__ import annotations

import random

from bitarena.domain import Decision, Quote, Side, TradeIntent, default_arena_mandate
from bitarena.firewall import EvalContext, Firewall, Signer, verify_certificate

EPS = 1e-6
ORDER_CAP = 2_000.0  # default_arena_mandate(10_000): order cap 2000, exposure 30000, lev 3


def _quote(mid: float = 100.0, ts: int = 1_000) -> Quote:
    return Quote(symbol="BTCUSDT", bid=mid - 0.05, ask=mid + 0.05, last=mid, ts=ts)


def test_firewall_safety_invariants_over_random_inputs():
    rng = random.Random(20_240_620)
    fw = Firewall(Signer.generate())  # a signer -> every verdict must be signed + verifiable
    mandate = default_arena_mandate(10_000)

    for _ in range(3_000):
        notional = rng.choice([
            rng.uniform(1.0, 100.0),
            rng.uniform(100.0, 2_500.0),
            rng.uniform(2_500.0, 1_000_000.0),
            rng.uniform(1_000_000.0, 1e9),
        ])
        intent = TradeIntent(
            agent_id="fuzz",
            symbol="BTCUSDT",
            side=rng.choice([Side.BUY, Side.SELL]),
            notional_usd=notional,
            reduce_only=rng.random() < 0.3,
        )
        halted = rng.random() < 0.1
        ctx = EvalContext(
            mandate=mandate,
            equity_usd=10_000.0,
            quote=_quote(),
            current_exposure_usd=rng.uniform(0.0, 40_000.0),
            daily_count=rng.randint(0, 250),
            halted=halted,
            now_ms=1_000,
            max_quote_age_ms=60_000,
        )
        v = fw.evaluate(intent, ctx)

        # INV1 — decision is always a valid verdict
        assert v.decision in (Decision.ALLOW, Decision.ALLOW_CAPPED, Decision.REJECT)
        # INV2 — every verdict is signed AND verifies (fail-closed signing), and the
        #        certificate's decision matches the verdict (no signing/decision skew)
        assert v.certificate is not None
        assert verify_certificate(v.certificate) is True
        assert v.certificate.decision is v.decision
        # INV3 — a halted arena rejects everything
        if halted:
            assert v.decision is Decision.REJECT
        # INV4 — an allowed order never exceeds the order cap or the request, and is positive
        if v.decision in (Decision.ALLOW, Decision.ALLOW_CAPPED):
            assert v.effective_notional_usd is not None
            assert 0.0 < v.effective_notional_usd <= ORDER_CAP + EPS
            assert v.effective_notional_usd <= notional + EPS
        # INV5 — a rejected order carries no executable size
        if v.decision is Decision.REJECT:
            assert v.effective_notional_usd is None or v.effective_notional_usd == 0.0


def test_firewall_tightening_never_increases_allowed_size():
    # Safety monotonicity: a STRICTER mandate (lower order cap) or MORE existing exposure can
    # never make the firewall more permissive. "Tightening can't loosen" — a core invariant.
    rng = random.Random(7)
    fw = Firewall(Signer.generate())

    def eff(intent, cap, exposure):
        base = default_arena_mandate(10_000)
        m = base.model_copy(
            update={"hard_caps": base.hard_caps.model_copy(update={"max_order_notional_usd": cap})}
        )
        v = fw.evaluate(intent, EvalContext(
            mandate=m, equity_usd=10_000.0, quote=_quote(),
            current_exposure_usd=exposure, now_ms=1_000, max_quote_age_ms=60_000,
        ))
        return v.effective_notional_usd or 0.0

    for _ in range(1_000):
        intent = TradeIntent(
            agent_id="mono", symbol="BTCUSDT",
            side=rng.choice([Side.BUY, Side.SELL]), notional_usd=rng.uniform(50.0, 10_000.0),
        )
        exposure = rng.uniform(0.0, 20_000.0)
        cap_hi = rng.uniform(1_000.0, 5_000.0)
        cap_lo = rng.uniform(100.0, cap_hi)  # cap_lo <= cap_hi (stricter order cap)

        # lowering the order cap never increases the allowed size
        assert eff(intent, cap_lo, exposure) <= eff(intent, cap_hi, exposure) + EPS
        # raising current exposure never increases the allowed size
        assert eff(intent, cap_hi, exposure + 5_000.0) <= eff(intent, cap_hi, exposure) + EPS


def test_firewall_never_allows_excluded_symbol_over_random_inputs():
    from bitarena.domain import UniverseConstraint

    rng = random.Random(99)
    fw = Firewall(Signer.generate())
    mandate = default_arena_mandate(10_000).model_copy(
        update={"universe": UniverseConstraint(exclude_symbols=("BTCUSDT",))}
    )
    for _ in range(500):
        intent = TradeIntent(
            agent_id="fuzz", symbol="BTCUSDT", side=rng.choice([Side.BUY, Side.SELL]),
            notional_usd=rng.uniform(1.0, 5_000.0), reduce_only=rng.random() < 0.5,
        )
        ctx = EvalContext(
            mandate=mandate, equity_usd=10_000.0, quote=_quote(),
            current_exposure_usd=0.0, daily_count=0, halted=False,
            now_ms=1_000, max_quote_age_ms=60_000,
        )
        v = fw.evaluate(intent, ctx)
        assert v.decision is Decision.REJECT  # an excluded symbol can never trade
        assert verify_certificate(v.certificate) is True


def test_session_gate_off_hours_tightening_is_monotone():
    # The session gate may only TIGHTEN: over random sizes/sides, an off-hours tokenized-equity
    # order is never allowed above the off-hours cap, and never MORE than the same order in-session
    # ("tightening can't loosen") — the gate's safety invariant across the input space.
    from datetime import datetime, timezone

    from bitarena.domain import InstrumentType
    from bitarena.domain.mandate import default_arena_mandate as mk
    from bitarena.domain.session import us_equity_session

    rng = random.Random(424_242)
    fw = Firewall(Signer.generate())
    mandate = mk(10_000, allowed_symbols=("RAAPLUSDT",))  # order cap 2000
    off_cap = ORDER_CAP * mandate.hard_caps.off_hours_notional_factor

    def _ts(y, mo, d, h):
        return int(datetime(y, mo, d, h, 0, tzinfo=timezone.utc).timestamp() * 1000)

    open_ts, closed_ts = _ts(2026, 6, 19, 18), _ts(2026, 6, 20, 18)  # Fri 14:00 ET / Sat
    assert us_equity_session(open_ts) == "open" and us_equity_session(closed_ts) == "closed"

    def eff(notional, side, now):
        q = Quote(symbol="RAAPLUSDT", bid=99.95, ask=100.05, last=100.0, ts=now)
        intent = TradeIntent(agent_id="sess", symbol="RAAPLUSDT", side=side,
                             notional_usd=notional, instrument=InstrumentType.TOKENIZED_EQUITY)
        v = fw.evaluate(intent, EvalContext(mandate=mandate, equity_usd=10_000.0, quote=q,
                                            now_ms=now, max_quote_age_ms=10**15))
        return v.effective_notional_usd or 0.0

    for _ in range(1_000):
        n = rng.uniform(1.0, 1e6)
        side = rng.choice([Side.BUY, Side.SELL])
        off, ins = eff(n, side, closed_ts), eff(n, side, open_ts)
        assert off <= off_cap + EPS          # off-hours never exceeds the tightened cap
        assert off <= ins + EPS              # tightening can't loosen

    # misconfiguration safety: even a factor > 1 can never OPEN headroom — the firewall clamps the
    # off-hours factor to [0, 1], so a bad mandate value still only tightens (never loosens).
    bad = mandate.model_copy(update={"hard_caps": mandate.hard_caps.model_copy(
        update={"off_hours_notional_factor": 2.0})})
    q = Quote(symbol="RAAPLUSDT", bid=99.95, ask=100.05, last=100.0, ts=closed_ts)
    v = fw.evaluate(
        TradeIntent(agent_id="bad", symbol="RAAPLUSDT", side=Side.BUY,
                    notional_usd=1e6, instrument=InstrumentType.TOKENIZED_EQUITY),
        EvalContext(mandate=bad, equity_usd=10_000.0, quote=q, now_ms=closed_ts, max_quote_age_ms=10**15))
    assert (v.effective_notional_usd or 0.0) <= ORDER_CAP + EPS  # clamp held; no loosening


def test_firewall_rejects_non_finite_size():
    # a malformed (NaN/inf) request must fail closed: rejected either at the model
    # boundary (ValidationError) or by the firewall — never turned into a capped trade.
    from pydantic import ValidationError

    fw = Firewall(Signer.generate())
    ctx = EvalContext(
        mandate=default_arena_mandate(10_000), equity_usd=10_000.0, quote=_quote(),
        now_ms=1_000, max_quote_age_ms=60_000,
    )
    for bad in (float("nan"), float("inf"), float("-inf")):
        for field in ("notional_usd", "quantity"):
            try:
                intent = TradeIntent(agent_id="x", symbol="BTCUSDT", side=Side.BUY, **{field: bad})
            except ValidationError:
                continue  # rejected at the model boundary — also fail-closed
            v = fw.evaluate(intent, ctx)
            assert v.decision is Decision.REJECT
            assert v.effective_notional_usd is None
            assert verify_certificate(v.certificate) is True


def test_firewall_fails_closed_on_internal_error(monkeypatch):
    # a safety firewall must never crash: an unexpected exception inside a gate becomes a signed
    # REJECT, never an exception out to the caller (a crash would be a fail-open).
    from bitarena.firewall import gates as _gates

    fw = Firewall(Signer.generate())

    def _boom(*_a, **_k):
        raise RuntimeError("synthetic gate crash")

    monkeypatch.setattr(_gates, "gate_halt", _boom)
    v = fw.evaluate(
        TradeIntent(agent_id="x", symbol="BTCUSDT", side=Side.BUY, notional_usd=50.0),
        EvalContext(mandate=default_arena_mandate(10_000), equity_usd=10_000.0, quote=_quote(),
                    now_ms=1_000, max_quote_age_ms=60_000),
    )
    assert v.decision is Decision.REJECT
    assert "internal error" in v.reason
    assert verify_certificate(v.certificate) is True  # even the fail-closed reject is signed
