"""The firewall: evaluate a TradeIntent against a mandate + context, return a Verdict.

Order of operations (all structural gates fail-closed → REJECT):

1. halt → expiry → universe → instrument → quote sanity → min-price → daily-count
   → requested-leverage. Any failure rejects immediately.
2. Normalize the requested notional (the larger of explicit notional and
   quantity x price; a quantity that cannot be priced is rejected).
3. Compute the largest notional that satisfies every sizing cap (per-order,
   total-exposure, leverage-on-exposure). If the request fits → ALLOW. If it
   does not but there is usable headroom → ALLOW_CAPPED at the headroom. If there
   is no headroom → REJECT.

Every decision is wrapped in an Ed25519-signed :class:`Certificate` when the
firewall holds a signer.
"""

from __future__ import annotations

import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..domain.intent import TradeIntent
from ..domain.mandate import Mandate
from ..domain.market import InstrumentType, Quote
from ..domain.session import us_equity_session
from ..domain.verdict import Certificate, Decision, GateResult, Verdict
from . import gates
from .regime import MarketRegime
from .signing import Signer, intent_hash, new_nonce, utc_now_iso

#: A trade smaller than this (after capping) is not worth executing → REJECT.
MIN_TRADABLE_NOTIONAL_USD = 1.0
_EPS = 1e-9


class EvalContext(BaseModel):
    """Everything the firewall needs about the world to rule on one intent."""

    model_config = ConfigDict(frozen=True)

    mandate: Mandate
    equity_usd: float
    quote: Quote | None = None
    current_exposure_usd: float = 0.0
    position_qty: float = 0.0  # signed current position in the symbol; lets the firewall
    #                            verify a reduce-only claim instead of trusting the flag
    daily_count: int = 0
    halted: bool = False
    regime: MarketRegime = MarketRegime.NORMAL  # fleet-wide kill-switch state (fast crash → reduce-only)
    now_ms: int | None = None
    max_quote_age_ms: int = 60_000


class Firewall:
    """Stateless evaluator. Holds only an optional signer for certificates."""

    def __init__(self, signer: Signer | None = None) -> None:
        self._signer = signer

    @classmethod
    def with_key(cls, path: Path | str) -> "Firewall":
        """Build a firewall whose certificates are signed by the key at ``path``."""
        return cls(Signer.load_or_create(path))

    @classmethod
    def with_settings(cls, settings) -> "Firewall":
        """Build a firewall using an env-injected key (b64) if present, else the key file."""
        from .signing import build_signer

        return cls(build_signer(settings.signing_key_b64, settings.signing_key_path))

    @property
    def issuer(self) -> str | None:
        return self._signer.fingerprint if self._signer else None

    def evaluate(self, intent: TradeIntent, ctx: EvalContext) -> Verdict:
        price = ctx.quote.mid if ctx.quote is not None else None

        structural: list[GateResult] = [
            gates.gate_halt(ctx.halted),
            gates.gate_expiry(ctx.mandate),
            gates.gate_universe(intent, ctx.mandate),
            gates.gate_instrument(intent, ctx.mandate),
            gates.gate_quote_sanity(ctx.quote, ctx.now_ms, ctx.max_quote_age_ms),
            gates.gate_min_price(ctx.mandate, price),
            gates.gate_daily_count(ctx.daily_count, ctx.mandate),
            gates.gate_leverage_request(intent, ctx.mandate),
            gates.gate_market_regime(
                ctx.regime, intent, ctx.position_qty,
                ctx.quote.mid if ctx.quote is not None else None,
            ),
        ]
        first_fail = next((g for g in structural if not g.passed), None)
        if first_fail is not None:
            return self._finalize(
                intent, Decision.REJECT, None,
                first_fail.detail or f"{first_fail.gate} failed", structural,
            )

        requested = self._requested_notional(intent, price)
        if requested is None or not math.isfinite(requested):
            failed = GateResult(
                gate="sizing", passed=False,
                detail="non-finite or unpriceable order size (fail-closed)",
            )
            return self._finalize(intent, Decision.REJECT, None, failed.detail, [*structural, failed])

        allowable, sizing = self._allowable_notional(intent, ctx, requested)
        all_gates = [*structural, *sizing]

        if allowable + _EPS >= requested:
            return self._finalize(intent, Decision.ALLOW, round(requested, 8), "within all limits", all_gates)
        if allowable >= MIN_TRADABLE_NOTIONAL_USD:
            capped = round(allowable, 2)
            return self._finalize(
                intent, Decision.ALLOW_CAPPED, capped,
                f"capped from ${requested:,.2f} to ${capped:,.2f}", all_gates,
            )
        return self._finalize(intent, Decision.REJECT, None, "no headroom under sizing caps", all_gates)

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _requested_notional(intent: TradeIntent, price: float | None) -> float | None:
        """Authoritative requested notional: larger of explicit and quantity x price."""
        explicit = intent.notional_usd
        implied: float | None = None
        if intent.quantity is not None:
            if price is None or price <= 0:
                return None
            implied = intent.quantity * price
            if implied != implied or implied <= 0:  # NaN / non-positive
                return None
        if explicit is not None and implied is not None:
            return max(explicit, implied)
        return explicit if explicit is not None else implied

    @staticmethod
    def _allowable_notional(
        intent: TradeIntent, ctx: EvalContext, requested: float
    ) -> tuple[float, list[GateResult]]:
        caps = ctx.mandate.hard_caps
        results: list[GateResult] = []

        order_cap = caps.max_order_notional_usd
        # Session gate: when an agent trades a tokenized US stock while the underlying market is
        # CLOSED, the rToken can dislocate from the (frozen) underlying and gap at re-open, so the
        # per-order cap is tightened — graduated containment (size down off-hours), not a reject.
        if (
            intent.instrument is InstrumentType.TOKENIZED_EQUITY
            and ctx.now_ms is not None
            and us_equity_session(ctx.now_ms) == "closed"
        ):
            tightened = order_cap * caps.off_hours_notional_factor
            results.append(
                GateResult(
                    gate="session",
                    passed=True,  # informational: tightens the cap, never opens headroom
                    limit=tightened,
                    attempted=requested,
                    detail=(
                        f"underlying US market closed — off-hours tokenized-equity cap "
                        f"x{caps.off_hours_notional_factor:g} (${order_cap:,.0f} -> ${tightened:,.0f})"
                    ),
                )
            )
            order_cap = tightened
        results.append(
            GateResult(
                gate="max_order_notional",
                passed=requested <= order_cap + _EPS,
                limit=order_cap,
                attempted=requested,
            )
        )
        allowable = order_cap

        # A reduce-only order is exempt from the exposure/leverage caps ONLY when it is a
        # *verified* genuine reduction (side opposes the position and does not exceed it — no
        # opening or flipping). The bare reduce_only flag is never trusted; the same check
        # guards the crash kill-switch, so it lives in one place (gates.is_genuine_reduction).
        price = ctx.quote.mid if ctx.quote is not None else None
        if not gates.is_genuine_reduction(intent, ctx.position_qty, price):
            # clamp at 0: a negative reported exposure must never *inflate* headroom past the caps
            exposure = max(0.0, ctx.current_exposure_usd)
            exposure_room = max(0.0, caps.max_total_exposure_usd - exposure)
            results.append(
                GateResult(
                    gate="max_total_exposure",
                    passed=requested <= exposure_room + _EPS,
                    limit=caps.max_total_exposure_usd,
                    attempted=exposure + requested,
                )
            )
            allowable = min(allowable, exposure_room)

            lev_ceiling = caps.max_leverage * ctx.equity_usd
            lev_room = max(0.0, lev_ceiling - exposure)
            results.append(
                GateResult(
                    gate="max_leverage_exposure",
                    passed=requested <= lev_room + _EPS,
                    limit=lev_ceiling,
                    attempted=ctx.current_exposure_usd + requested,
                )
            )
            allowable = min(allowable, lev_room)

        return min(allowable, requested), results

    def _finalize(
        self,
        intent: TradeIntent,
        decision: Decision,
        effective_notional: float | None,
        reason: str,
        gate_results: list[GateResult],
    ) -> Verdict:
        certificate: Certificate | None = None
        if self._signer is not None:
            unsigned = Certificate(
                intent_hash=intent_hash(intent),
                decision=decision,
                effective_notional_usd=effective_notional,
                issued_at=utc_now_iso(),
                issuer="",
                nonce=new_nonce(),
            )
            certificate = self._signer.sign_certificate(unsigned)
        return Verdict(
            decision=decision,
            reason=reason,
            gates=tuple(gate_results),
            effective_notional_usd=effective_notional,
            certificate=certificate,
        )
