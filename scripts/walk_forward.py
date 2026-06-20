"""Walk-forward robustness of the arena agents on REAL Bitget data.

    uv run python scripts/walk_forward.py --symbol BTCUSDT --instrument perp --bars 1000 --folds 5

Splits the history into disjoint folds, runs the arena on each, and reports per-agent
stability (mean return, std, % positive folds, consistency). Writes evidence/walk_forward.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.connectors import synthetic_series
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import InstrumentType
from bitarena.research import walk_forward_arena


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward robustness of arena agents.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", choices=["perp", "spot"], default="perp")
    parser.add_argument("--bars", type=int, default=1000)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--out", default="evidence/walk_forward.json")
    args = parser.parse_args()

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT
    client = BitgetPublicData()
    candles = client.get_candles(args.symbol, instrument, timeframe=args.timeframe, limit=args.bars)
    client.close()
    source = f"bitget:{args.timeframe}:{len(candles)}bars"
    if len(candles) < 100:
        candles = synthetic_series(args.symbol, n=args.bars, seed=11, drift=0.0008, vol=0.012)
        source = "synthetic"

    report = walk_forward_arena(candles, symbol=args.symbol, instrument=instrument, folds=args.folds)
    report["source"] = source
    report["symbol"] = args.symbol

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"walk-forward {args.symbol} ({source}) — {report['folds']} folds")
    print(f"{'agent':<20}{'mean_ret':>10}{'std':>9}{'pos_folds':>11}{'consistency':>13}")
    rows = sorted(report["summary"].items(), key=lambda kv: kv[1]["mean_return"], reverse=True)
    for aid, s in rows:
        print(f"{aid:<20}{s['mean_return']*100:>9.2f}%{s['std_return']*100:>8.2f}%{s['pct_positive_folds']*100:>10.0f}%{str(s['consistency']):>13}")
    print(f"evidence -> {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
