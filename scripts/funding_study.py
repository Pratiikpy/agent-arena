"""Honest funding-carry edge study on REAL Bitget funding-rate history.

    uv run python scripts/funding_study.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --limit 300

Fetches real perpetual funding history from Bitget, computes the delta-neutral carry
(passive + adaptive sweep), validates with walk-forward + Deflated Sharpe, and writes
evidence/funding_carry.json. Reports the real numbers — including when the edge is thin.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.connectors.bitget import BitgetPublicData
from bitarena.research.funding_carry import study


def main() -> None:
    parser = argparse.ArgumentParser(description="Funding-carry edge study on real Bitget data.")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--out", default="evidence/funding_carry.json")
    args = parser.parse_args()

    client = BitgetPublicData()
    report: dict = {"intervals_per_year": 1095, "source": "bitget:history-fund-rate", "symbols": {}}
    try:
        for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
            hist = client.get_funding_history(sym, limit=args.limit)
            rates = [h["funding_rate"] for h in hist]
            if len(rates) < 20:
                report["symbols"][sym] = {"error": f"insufficient funding history ({len(rates)})"}
                continue
            report["symbols"][sym] = study(rates)
    finally:
        client.close()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"{'symbol':<10}{'intervals':>10}{'pos%':>7}{'passive_ann':>13}{'sharpe':>9}{'maxDD':>9}{'adapt_ann':>11}{'DSR':>7}")
    for sym, s in report["symbols"].items():
        if "error" in s:
            print(f"{sym:<10} {s['error']}")
            continue
        pc = s["passive_carry"]
        ab = s["adaptive_best"]
        print(
            f"{sym:<10}{s['intervals']:>10}{s['pct_positive_funding']*100:>6.0f}%"
            f"{pc['annualized_return']*100:>12.2f}%{str(pc['sharpe_annualized']):>9}"
            f"{pc['max_drawdown']*100:>8.2f}%{ab['annualized_return']*100:>10.2f}%{str(s['deflated_sharpe_best']):>7}"
        )
    print(f"evidence -> {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
