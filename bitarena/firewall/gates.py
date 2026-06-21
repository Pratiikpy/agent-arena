"""Pure, individually testable risk gates.

Each gate takes only what it needs and returns a :class:`GateResult`. Gates never
raise and never mutate; the :class:`~bitarena.firewall.firewall.Firewall` composes
them. Every gate is fail-closed: missing or unparseable inputs produce a failing
result rather than a pass.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

from ..domain.mandate import Mandate
from ..domain.market import Quote, Side
from ..domain.intent import TradeIntent
from ..domain.verdict import GateResult
from .regime import MarketRegime


def gate_halt(halted: bool) -> GateResult:
    return GateResult(gate="halt", passed=not halted, detail="trading halted" if halted else "")


def gate_expiry(mandate: Mandate) -> GateResult:
    if not mandate.expires_at:
        return GateResult(gate="expiry", passed=True)
    try:
        expires = datetime.fromisoformat(mandate.expires_at)
    except (TypeError, ValueError):
        return GateResult(gate="expiry", passed=False, detail="unparseable expiry (fail-closed)")
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    passed = datetime.now(timezone.utc) < expires
    return GateResult(gate="expiry", passed=passed, detail="" if passed else "mandate expired")


def gate_universe(intent: TradeIntent, mandate: Mandate) -> GateResult:
    symbol = intent.normalized_symbol
    if mandate.universe.permits(symbol):
        return GateResult(gate="universe", passed=True)
    return GateResult(gate="universe", passed=False, detail=f"{symbol} not in permitted universe")


def gate_min_price(mandate: Mandate, price: float | None) -> GateResult:
    floor = mandate.universe.min_price_usd
    if floor is None:
        return GateResult(gate="min_price", passed=True)
    if price is None:
        return GateResult(gate="min_price", passed=False, detail="no price to check floor (fail-closed)")
    passed = price >= floor
    return GateResult(gate="min_price", passed=passed, limit=floor, attempted=price)


def gate_instrument(intent: TradeIntent, mandate: Mandate) -> GateResult:
    allowed = mandate.hard_caps.allowed_instruments
    passed = intent.instrument in allowed
    detail = "" if passed else f"{intent.instrument.value} not in allowed instruments"
    return GateResult(gate="instrument", passed=passed, detail=detail)


def gate_quote_sanity(
    quote: Quote | None, now_ms: int | None, max_age_ms: int | None
) -> GateResult:
    if quote is None:
        return GateResult(gate="quote", passed=False, detail="no quote available (fail-closed)")
    # A one-sided, negative, or non-finite book is unusable for execution. Fail closed rather than
    # trust the `last`-price fallback that quote.mid uses for display when bid/ask are missing.
    if not (math.isfinite(quote.bid) and math.isfinite(quote.ask)) or quote.bid <= 0 or quote.ask <= 0:
        return GateResult(gate="quote", passed=False, detail="malformed book: non-positive or non-finite bid/ask (fail-closed)")
    if quote.is_crossed:
        return GateResult(gate="quote", passed=False, detail="crossed/locked order book")
    if quote.mid <= 0:
        return GateResult(gate="quote", passed=False, detail="non-positive price")
    if max_age_ms is not None:
        if now_ms is None:  # a freshness threshold is set but there is no clock -> fail closed
            return GateResult(
                gate="quote", passed=False, detail="no clock to evaluate quote age (fail-closed)"
            )
        age = now_ms - quote.ts
        if age > max_age_ms:
            return GateResult(
                gate="quote", passed=False, detail="stale quote", limit=max_age_ms, attempted=age
            )
    return GateResult(gate="quote", passed=True)


def gate_daily_count(daily_count: int, mandate: Mandate) -> GateResult:
    cap = mandate.hard_caps.max_trades_per_day
    passed = daily_count < cap
    detail = "" if passed else "daily trade limit reached"
    return GateResult(gate="daily_count", passed=passed, detail=detail, limit=cap, attempted=daily_count)


def gate_leverage_request(intent: TradeIntent, mandate: Mandate) -> GateResult:
    cap = mandate.hard_caps.max_leverage
    passed = intent.leverage <= cap + 1e-9
    detail = "" if passed else "requested leverage exceeds cap"
    return GateResult(gate="leverage", passed=passed, detail=detail, limit=cap, attempted=intent.leverage)


def is_genuine_reduction(
    intent: TradeIntent, position_qty: float, price: float | None
) -> bool:
    """True only if the order genuinely reduces an existing position: it is reduce-only, its
    side opposes the position sign, and its notional does not exceed the position (so it can
    neither open nor flip). The ``reduce_only`` flag alone is never trusted — this is what
    both the exposure-cap exemption and the kill-switch rely on, so a fake reduce-only order
    can neither bypass the caps nor slip past the crash kill-switch."""
    if not intent.reduce_only or price is None or price <= 0:
        return False
    opposes = (
        (intent.side is Side.SELL and position_qty > 0)
        or (intent.side is Side.BUY and position_qty < 0)
    )
    if not opposes:
        return False
    requested = intent.notional_usd or 0.0
    if intent.quantity is not None:
        requested = max(requested, intent.quantity * price)
    return requested <= abs(position_qty) * price + 1e-9


def gate_market_regime(
    regime: MarketRegime,
    intent: TradeIntent,
    position_qty: float = 0.0,
    price: float | None = None,
) -> GateResult:
    """Fleet-wide kill-switch: in a fast crash (``FAST_RISK_OFF``) only a *verified* genuine
    reduction passes — every agent is forced to stop adding exposure at once. The reduce-only
    flag alone is not enough (a fake reduce-only on a flat book cannot slip through), so an
    agent cannot use it to open or average into a position mid-crash. ``NORMAL`` always passes."""
    if regime is not MarketRegime.FAST_RISK_OFF:
        return GateResult(
            gate="market_regime",
            passed=True,
            detail="" if regime is MarketRegime.NORMAL else regime.value,
        )
    if is_genuine_reduction(intent, position_qty, price):
        return GateResult(gate="market_regime", passed=True, detail="fast risk-off: de-risking permitted")
    return GateResult(
        gate="market_regime",
        passed=False,
        detail="market kill-switch engaged (fast risk-off): de-risking (reduce-only) trades only",
    )
