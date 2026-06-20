"""Pure, individually testable risk gates.

Each gate takes only what it needs and returns a :class:`GateResult`. Gates never
raise and never mutate; the :class:`~bitarena.firewall.firewall.Firewall` composes
them. Every gate is fail-closed: missing or unparseable inputs produce a failing
result rather than a pass.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..domain.mandate import Mandate
from ..domain.market import Quote
from ..domain.intent import TradeIntent
from ..domain.verdict import GateResult


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
    if quote.is_crossed:
        return GateResult(gate="quote", passed=False, detail="crossed/locked order book")
    if quote.mid <= 0:
        return GateResult(gate="quote", passed=False, detail="non-positive price")
    if now_ms is not None and max_age_ms is not None:
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
