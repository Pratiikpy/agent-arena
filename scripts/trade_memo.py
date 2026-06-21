"""Generate ONE signed trade memo: vet a trade through the firewall, then write a named-section,
signed explanation of the decision (thesis / signals / risk / verdict) to evidence/trade_memo.json.

The prose is written by Qwen when a key is present and a factual template otherwise; every number
comes from the verdict and the analyst signals. Example:
    uv run python scripts/trade_memo.py --symbol BTCUSDT --notional 50000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.agents.memo import build_memo, verify_memo
from bitarena.config import load_settings
from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.domain import InstrumentType, Side, TradeIntent, default_arena_mandate
from bitarena.firewall import EvalContext, Firewall
from bitarena.llm import QwenClient
from bitarena.perception.agent_hub import agent_hub_sources
from bitarena.perception.base import aggregate
from bitarena.perception.factors import QuantFactorPerception
from bitarena.perception.market_features import TechnicalPerception


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate one signed trade memo.")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--notional", type=float, default=50_000.0)  # oversized -> shows the cap
    ap.add_argument("--equity", type=float, default=10_000.0)
    ap.add_argument("--out", default="evidence/trade_memo.json")
    args = ap.parse_args()

    inst = InstrumentType.PERP
    market = ReplayMarketData({args.symbol: synthetic_series(args.symbol, n=120, seed=1)})
    market.set_cursor(119)
    quote = market.get_quote(args.symbol, inst)
    sources = [TechnicalPerception(), QuantFactorPerception(), *agent_hub_sources(None)]
    bundle = aggregate(args.symbol, quote.ts, sources, market, inst)

    intent = TradeIntent(agent_id="swarm", symbol=args.symbol, side=Side.BUY,
                         instrument=inst, notional_usd=args.notional, ts=quote.ts)
    fw = Firewall.with_key(load_settings().signing_key_path)
    ctx = EvalContext(mandate=default_arena_mandate(args.equity, allowed_symbols=(args.symbol.upper(),)),
                      equity_usd=args.equity, quote=quote, now_ms=quote.ts, max_quote_age_ms=10 ** 15)
    verdict = fw.evaluate(intent, ctx)
    memo = build_memo(intent=intent, verdict=verdict, bundle=bundle,
                      signer=fw._signer, llm=QwenClient.from_settings())

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(memo, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: decision={memo['decision']} source={memo['source']} "
          f"verifies={verify_memo(memo)}")


if __name__ == "__main__":
    main()
