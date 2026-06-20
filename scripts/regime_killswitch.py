"""Quantify the firewall's fleet-wide kill-switch in a flash crash.

A reckless "buy the dip" agent adds $5k of exposure every bar. We run it twice over the
same crash path — once UNPROTECTED (every order fills) and once behind the firewall, whose
market-regime kill-switch flips to FAST_RISK_OFF on a sharp drawdown and then permits only
de-risking. The kill-switch freezes new exposure as the market falls, capping the loss; the
unprotected agent keeps buying all the way down. Every blocked order is a signed REJECT.

    uv run python scripts/regime_killswitch.py            # writes evidence/regime_killswitch.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.config import load_settings
from bitarena.domain import Side, TradeIntent, default_arena_mandate
from bitarena.domain.market import Quote
from bitarena.firewall import EvalContext, Firewall, assess_regime, verify_certificate
from bitarena.firewall.regime import MarketRegime


def build_crash(*, n_flat: int = 10, n_crash: int = 12, start: float = 63_000.0, drop: float = 0.16) -> list[float]:
    """Flat, then a fast linear sell-off to ``start*(1-drop)`` over ``n_crash`` bars."""
    prices = [start] * n_flat
    for i in range(1, n_crash + 1):
        prices.append(round(start * (1 - drop * i / n_crash), 2))
    return prices


def run(prices: list[float], *, protected: bool, order_usd: float = 10_000.0) -> dict:
    fw = Firewall.with_key(load_settings().signing_key_path)  # canonical arena issuer
    mandate = default_arena_mandate(100_000.0, allowed_symbols=("BTCUSDT",))  # caps generous; only the kill-switch bites
    cash, qty = 100_000.0, 0.0
    timeline: list[dict] = []
    blocked, sample_reject = 0, None

    for i, price in enumerate(prices):
        regime = assess_regime(prices[: i + 1])
        intent = TradeIntent(agent_id="reckless-dip-buyer", symbol="BTCUSDT", side=Side.BUY, notional_usd=order_usd)
        if protected:
            quote = Quote(symbol="BTCUSDT", bid=price - 1, ask=price + 1, last=price, ts=1_000 + i)
            ctx = EvalContext(
                mandate=mandate, equity_usd=cash + qty * price, quote=quote,
                current_exposure_usd=abs(qty) * price, position_qty=qty,
                regime=regime, now_ms=1_000 + i, max_quote_age_ms=10 ** 9,
            )
            v = fw.evaluate(intent, ctx)
            decision = v.decision.value
            filled = v.effective_notional_usd if v.allowed else 0.0
            if not v.allowed:
                blocked += 1
                if sample_reject is None and regime is MarketRegime.FAST_RISK_OFF and v.certificate:
                    sample_reject = {
                        "certificate": v.certificate.model_dump(),
                        "certificate_valid": verify_certificate(v.certificate),
                        "reason": v.reason,
                    }
        else:
            decision, filled = "FILL", order_usd

        if filled:
            qty += filled / price
            cash -= filled
        timeline.append({
            "step": i, "price": price, "regime": regime.value,
            "decision": decision, "filled_usd": round(filled, 2),
            "position_qty": round(qty, 6), "equity_usd": round(cash + qty * price, 2),
        })

    return {
        "final_equity_usd": round(cash + qty * prices[-1], 2),
        "final_position_qty": round(qty, 6),
        "orders_blocked": blocked,
        "timeline": timeline,
        "sample_signed_reject": sample_reject,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Quantify the firewall kill-switch in a flash crash.")
    ap.add_argument("--out", default="evidence/regime_killswitch.json")
    args = ap.parse_args()

    prices = build_crash()
    protected = run(prices, protected=True)
    unprotected = run(prices, protected=False)
    saved = round(protected["final_equity_usd"] - unprotected["final_equity_usd"], 2)

    result = {
        "scenario": {
            "description": "reckless 'buy the dip' agent (+$5k exposure/bar) through a ~16% flash crash",
            "bars": len(prices),
            "start_price": prices[0],
            "end_price": prices[-1],
            "crash_pct": round((prices[0] - prices[-1]) / prices[0] * 100, 1),
        },
        "protected": protected,
        "unprotected": unprotected,
        "kill_switch_engaged_at_step": next(
            (t["step"] for t in protected["timeline"] if t["regime"] == "FAST_RISK_OFF"), None
        ),
        "loss_avoided_usd": saved,
        "summary": (
            f"Kill-switch blocked {protected['orders_blocked']} new-exposure orders during the crash; "
            f"protected fleet ended at ${protected['final_equity_usd']:,.0f} vs "
            f"${unprotected['final_equity_usd']:,.0f} unprotected — ${saved:,.0f} of loss avoided."
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(result["summary"])
    print(f"kill-switch engaged at step {result['kill_switch_engaged_at_step']}; wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
