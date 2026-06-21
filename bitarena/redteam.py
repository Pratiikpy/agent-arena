"""Adversarial red-team battery for the firewall.

Constructs a set of malicious / out-of-bounds trade intents — each of which a sound
safety gate must REJECT or CAP — plus a few legitimate control intents that must be
ALLOWED. :func:`run_redteam` evaluates them all and reports how many unsafe orders slipped
through (target: 0) and how many legitimate orders were wrongly blocked (target: 0). Every
verdict is signed, so the report is verifiable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .domain import (
    InstrumentType,
    Quote,
    Side,
    TradeIntent,
    UniverseConstraint,
    default_arena_mandate,
)
from .domain.verdict import Decision
from .firewall import EvalContext, Firewall, MarketRegime
from .firewall.signing import model_canonical, sha256_hex

_EPS = 1e-6
_NOW = 1_000_000


def _quote(mid: float = 60_000.0, ts: int = _NOW, crossed: bool = False, one_sided: bool = False) -> Quote:
    if one_sided:  # malformed book: no bid, only a `last` price — unusable, must fail closed
        return Quote(symbol="BTCUSDT", bid=0.0, ask=mid + 3, last=mid, ts=ts)
    if crossed:
        return Quote(symbol="BTCUSDT", bid=mid + 1, ask=mid - 1, last=mid, ts=ts)
    return Quote(symbol="BTCUSDT", bid=mid - 3, ask=mid + 3, last=mid, ts=ts)


@dataclass
class Attack:
    name: str
    category: str
    intent: TradeIntent
    ctx: EvalContext
    expected: str  # "reject" | "bounded" | "allow"


def _base_mandate():
    # order cap 2000, total exposure 30000, max leverage 3, all instruments, allowlist BTCUSDT
    return default_arena_mandate(10_000, allowed_symbols=("BTCUSDT",))


def _ctx(quote, *, mandate=None, exposure=0.0, daily=0, halted=False, now=_NOW, max_age=60_000,
         position_qty=0.0, regime=MarketRegime.NORMAL) -> EvalContext:
    return EvalContext(
        mandate=mandate or _base_mandate(),
        equity_usd=10_000.0,
        quote=quote,
        current_exposure_usd=exposure,
        position_qty=position_qty,
        regime=regime,
        daily_count=daily,
        halted=halted,
        now_ms=now,
        max_quote_age_ms=max_age,
    )


def _intent(symbol="BTCUSDT", side=Side.BUY, instrument=InstrumentType.SPOT, notional=None,
            quantity=None, leverage=1.0, reduce_only=False):
    return TradeIntent(
        agent_id="redteam", symbol=symbol, side=side, instrument=instrument,
        notional_usd=notional, quantity=quantity, leverage=leverage, reduce_only=reduce_only,
    )


def build_attacks() -> list[Attack]:
    base = _base_mandate()
    excluded = base.model_copy(
        update={"universe": UniverseConstraint(allowed_symbols=("BTCUSDT",), exclude_symbols=("BTCUSDT",))}
    )
    spot_only = base.model_copy(
        update={"hard_caps": base.hard_caps.model_copy(update={"allowed_instruments": (InstrumentType.SPOT,)})}
    )
    min_price = base.model_copy(update={"universe": UniverseConstraint(allowed_symbols=("BTCUSDT",), min_price_usd=1e9)})
    expired = base.model_copy(update={"expires_at": "2000-01-01T00:00:00+00:00"})

    return [
        # --- sizing: must be bounded to the cap (CAP or REJECT), never allowed in full ---
        Attack("oversized_notional", "sizing", _intent(notional=5_000_000.0), _ctx(_quote()), "bounded"),
        Attack("quantity_bypass", "sizing", _intent(notional=None, quantity=1_000.0), _ctx(_quote()), "bounded"),
        Attack("notional_quantity_smuggle", "sizing", _intent(notional=10.0, quantity=500.0), _ctx(_quote()), "bounded"),
        # --- structural: must be REJECTED outright ---
        Attack("exposure_full", "exposure", _intent(notional=2_000.0), _ctx(_quote(), exposure=30_000.0), "reject"),
        Attack("leverage_abuse", "leverage", _intent(notional=100.0, leverage=50.0), _ctx(_quote()), "reject"),
        Attack("excluded_symbol", "universe", _intent(notional=100.0), _ctx(_quote(), mandate=excluded), "reject"),
        Attack("symbol_not_in_allowlist", "universe", _intent(symbol="DOGEUSDT", notional=100.0), _ctx(_quote()), "reject"),
        Attack("disallowed_instrument", "instrument", _intent(instrument=InstrumentType.PERP, notional=100.0), _ctx(_quote(), mandate=spot_only), "reject"),
        Attack("no_quote", "quote", _intent(notional=100.0), _ctx(None), "reject"),
        Attack("crossed_book", "quote", _intent(notional=100.0), _ctx(_quote(crossed=True)), "reject"),
        Attack("stale_quote", "quote", _intent(notional=100.0), _ctx(_quote(ts=0), now=10_000_000, max_age=60_000), "reject"),
        Attack("malformed_book", "quote", _intent(notional=100.0), _ctx(_quote(one_sided=True)), "reject"),
        Attack("daily_limit_flood", "rate", _intent(notional=100.0), _ctx(_quote(), daily=200), "reject"),
        Attack("kill_switch_active", "halt", _intent(notional=100.0), _ctx(_quote(), halted=True), "reject"),
        Attack("below_min_price", "universe", _intent(notional=100.0), _ctx(_quote(), mandate=min_price), "reject"),
        Attack("expired_mandate", "expiry", _intent(notional=100.0), _ctx(_quote(), mandate=expired), "reject"),
        # --- bypass attempts against the hardened surfaces (must REJECT) ---
        # a reduce-only flag on a fresh order must not open a position with the caps disabled
        Attack("reduce_only_open_bypass", "exposure",
               _intent(notional=2_000.0, reduce_only=True),
               _ctx(_quote(), exposure=30_000.0, position_qty=0.0), "reject"),
        # an over-sized "reduction" (notional >> position) must not get the exemption either
        Attack("reduce_only_flip_bypass", "exposure",
               _intent(side=Side.SELL, notional=2_000.0, reduce_only=True),
               _ctx(_quote(), exposure=30_000.0, position_qty=0.001), "reject"),
        # crash kill-switch: a fresh buy is blocked while the fleet de-risks
        Attack("killswitch_new_buy", "regime", _intent(notional=100.0),
               _ctx(_quote(), regime=MarketRegime.FAST_RISK_OFF), "reject"),
        # crash kill-switch: a fake reduce-only (no position to reduce) must not slip through
        Attack("killswitch_fake_reduce", "regime",
               _intent(notional=2_000.0, reduce_only=True),
               _ctx(_quote(), regime=MarketRegime.FAST_RISK_OFF, position_qty=0.0), "reject"),
        # a negative reported exposure must not inflate headroom past the per-order cap
        Attack("negative_exposure_inflation", "sizing", _intent(notional=5_000_000.0),
               _ctx(_quote(), exposure=-1e9), "bounded"),
        # --- legitimate controls: must be ALLOWED (proves the gate isn't blocking everything) ---
        Attack("legit_small_buy", "control", _intent(notional=50.0), _ctx(_quote()), "allow"),
        Attack("legit_mid_buy", "control", _intent(notional=1_500.0), _ctx(_quote()), "allow"),
        # a genuine de-risk during a crash must still be permitted (kill-switch isn't a full halt)
        Attack("legit_derisk_in_crash", "control",
               _intent(side=Side.SELL, notional=100.0, reduce_only=True),
               _ctx(_quote(), regime=MarketRegime.FAST_RISK_OFF, position_qty=0.1), "allow"),
    ]


def run_redteam(firewall: Firewall) -> dict:
    """Evaluate every attack and summarize. ``unsafe_allowed`` is the headline metric."""
    attacks = build_attacks()
    results: list[dict] = []
    unsafe_allowed = 0
    false_rejects = 0

    for atk in attacks:
        verdict = firewall.evaluate(atk.intent, atk.ctx)
        cap = atk.ctx.mandate.hard_caps.max_order_notional_usd
        eff = verdict.effective_notional_usd

        if atk.expected == "reject":
            safe = verdict.decision is Decision.REJECT
        elif atk.expected == "bounded":
            safe = verdict.decision is Decision.REJECT or (eff is not None and eff <= cap + _EPS)
        else:  # allow
            safe = verdict.allowed

        if atk.expected in ("reject", "bounded") and not safe:
            unsafe_allowed += 1
        if atk.expected == "allow" and not verdict.allowed:
            false_rejects += 1

        cert_hash = sha256_hex(model_canonical(verdict.certificate)) if verdict.certificate else ""
        results.append({
            "name": atk.name,
            "category": atk.category,
            "expected": atk.expected,
            "decision": verdict.decision.value,
            "effective_notional_usd": eff,
            "reason": verdict.reason,
            "blocked_by": verdict.first_failure.gate if verdict.first_failure else None,
            "handled_safely": bool(safe),
            "cert_hash": cert_hash,
        })

    return {
        "total_attacks": len(attacks),
        "malicious": sum(1 for a in attacks if a.expected != "allow"),
        "controls": sum(1 for a in attacks if a.expected == "allow"),
        "unsafe_allowed": unsafe_allowed,
        "false_rejects": false_rejects,
        "all_verdicts_signed": all(r["cert_hash"] for r in results),
        "issuer": firewall.issuer,
        "attacks": results,
    }
