"""Run ONE Qwen multi-analyst debate on a live market snapshot, then gate it.

This is the demo centerpiece: perceive (technicals + 5 Agent Hub Skills) -> Qwen
bull/bear/risk debate -> a sized intent -> the firewall returns a signed verdict.
Without a Qwen key it prints the deterministic fallback decision instead, so it always
runs. Writes evidence/llm_debate.json.

Example:
    uv run python scripts/llm_debate.py --symbol BTCUSDT --instrument perp
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.agents import AgentObservation, LLMDebateSwarm
from bitarena.config import load_settings
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.connectors.bitget import BitgetPublicData


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Qwen analyst debate and gate the result.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", choices=["perp", "spot"], default="perp")
    parser.add_argument("--source", choices=["bitget", "synthetic"], default="bitget")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--out", default="evidence/llm_debate.json")
    args = parser.parse_args()

    from bitarena.domain import InstrumentType
    from bitarena.firewall import EvalContext, Firewall, verify_certificate

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT

    if args.source == "bitget":
        client = BitgetPublicData()
        candles = client.get_candles(args.symbol, instrument, timeframe="1m", limit=120)
        client.close()
        if len(candles) >= 40:
            market = ReplayMarketData({args.symbol: candles})
            market.set_cursor(len(candles) - 1)
            source = f"bitget:{len(candles)}bars"
        else:
            market = ReplayMarketData({args.symbol: synthetic_series(args.symbol, n=120, seed=1)})
            market.set_cursor(119)
            source = "synthetic(fallback)"
    else:
        market = ReplayMarketData({args.symbol: synthetic_series(args.symbol, n=120, seed=1)})
        market.set_cursor(119)
        source = "synthetic"

    quote = market.get_quote(args.symbol, instrument)
    settings = load_settings()
    agent = LLMDebateSwarm(decide_every=1)  # force an LLM call this single tick

    obs = AgentObservation(
        symbol=args.symbol,
        instrument=instrument,
        ts=quote.ts,
        equity_usd=args.equity,
        position_qty=0.0,
        price=quote.mid,
        market=market,
    )
    intent = agent.decide(obs)

    firewall = Firewall.with_key(settings.signing_key_path)
    out: dict = {
        "symbol": args.symbol,
        "instrument": instrument.value,
        "source": source,
        "qwen_available": agent._llm.available(),
        "decision_source": agent.last_source,
        "rationale": agent.last_rationale,
        "signals": [
            {"name": s.name, "source": s.source, "value": round(s.value, 3), "confidence": s.confidence}
            for s in (agent.last_bundle.signals if agent.last_bundle else ())
        ],
        "net_signal": round(agent.last_bundle.net_signal, 3) if agent.last_bundle else None,
        "agreement": round(agent.last_bundle.agreement, 3) if agent.last_bundle else None,
    }

    if intent is None:
        out["intent"] = None
        out["verdict"] = {"decision": "HOLD", "reason": "no conviction -> no order"}
    else:
        from bitarena.domain import default_arena_mandate

        mandate = default_arena_mandate(args.equity, allowed_symbols=(args.symbol.upper(),))
        ctx = EvalContext(
            mandate=mandate, equity_usd=args.equity, quote=quote,
            current_exposure_usd=0.0, now_ms=quote.ts, max_quote_age_ms=10 ** 15,
        )
        verdict = firewall.evaluate(intent, ctx)
        out["intent"] = {"side": intent.side.value, "notional_usd": round(intent.notional_usd or 0, 2)}
        out["verdict"] = {
            "decision": verdict.decision.value,
            "reason": verdict.reason,
            "effective_notional_usd": verdict.effective_notional_usd,
            "certificate_valid": verify_certificate(verdict.certificate) if verdict.certificate else None,
        }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
