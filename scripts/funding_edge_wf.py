"""Walk-forward characterization of the funding-carry agent on real Bitget data.

    uv run python scripts/funding_edge_wf.py --symbol BTCUSDT --folds 5

Splits one symbol's real perp history into disjoint folds and, on each, runs the
funding-carry agent vs buy-hold with the overlapping funding, reporting per-fold excess
return, win rate, and real carry. Honest: shows whether the edge is time-stable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import InstrumentType
from bitarena.research import funding_agent_walk_forward


def main() -> None:
    parser = argparse.ArgumentParser(description="Funding-carry agent walk-forward on real Bitget data.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--bars", type=int, default=1000)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--out", default="evidence/funding_edge_walkforward.json")
    args = parser.parse_args()

    client = BitgetPublicData()
    candles = client.get_candles(args.symbol, InstrumentType.PERP, timeframe="1h", limit=args.bars)
    funding = client.get_funding_history(args.symbol, limit=400) if len(candles) >= 50 else []
    client.close()
    if len(candles) < 50 or not funding:
        print(f"insufficient real data (candles={len(candles)}, funding={len(funding)}) — needs network")
        return

    report = funding_agent_walk_forward(candles, funding, folds=args.folds, symbol=args.symbol)
    report["symbol"] = args.symbol
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"funding-carry walk-forward on real {args.symbol} perp — {report['folds']} folds")
    print(f"{'fold':<6}{'bars':>6}{'carry_ret':>11}{'buyhold':>10}{'excess':>10}{'carry$':>10}")
    for r in report["per_fold"]:
        print(f"{r['fold']:<6}{r['bars']:>6}{r['funding_carry_return']*100:>10.2f}%{r['buyhold_return']*100:>9.2f}%{r['excess']*100:>9.2f}%{r['carry_usd']:>10.2f}")
    print(
        f"mean excess vs buy-hold {report['mean_excess_vs_buyhold']*100:+.2f}% | "
        f"beats buy-hold {report['beats_buyhold_rate']*100:.0f}% of folds | total carry ${report['total_carry_usd']:.2f}"
    )
    print(f"evidence -> {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
