"""Measure the net, fee-aware delta-neutral funding carry on real Bitget history and write a
signed report to evidence/delta_neutral_carry.json.

Long spot + short perp: price risk cancels, the short perp leg collects funding, fees are charged
on entry and exit. The output is a floor-quality estimate of a real, explainable yield.

Example:
    uv run python scripts/delta_neutral_carry.py --symbols BTCUSDT,ETHUSDT,SOLUSDT --limit 300
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.connectors.bitget import BitgetPublicData
from bitarena.firewall.signing import build_signer, sign_payload
from bitarena.research.delta_neutral import delta_neutral_carry


def main() -> None:
    ap = argparse.ArgumentParser(description="Net delta-neutral funding carry on real Bitget data.")
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--out", default="evidence/delta_neutral_carry.json")
    ap.add_argument("--key", default=".keys/arena.pem")
    args = ap.parse_args()

    client = BitgetPublicData()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    report: dict = {"source": "bitget:history-fund-rate", "fee_bps_per_leg": args.fee_bps,
                    "symbols": {}}
    for sym in symbols:
        try:
            rates = client.get_funding_history(sym, limit=args.limit)
        except Exception as exc:  # network/parse — record and continue
            report["symbols"][sym] = {"error": str(exc)}
            continue
        report["symbols"][sym] = delta_neutral_carry(rates, fee_bps_per_leg=args.fee_bps)

    signed = sign_payload(report, build_signer(None, args.key))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(signed, indent=2), encoding="utf-8")

    print(f"wrote {out}")
    for sym, r in report["symbols"].items():
        if r.get("insufficient") or r.get("error"):
            print(f"  {sym}: {r.get('error', 'insufficient history')}")
            continue
        b = r["best"]
        print(f"  {sym}: gross {b['gross_annualized_return'] * 100:+.2f}%/yr · "
              f"net(maker) {b['net_annualized_maker'] * 100:+.2f}% · net(taker) {b['annualized_return'] * 100:+.2f}% "
              f"· {b['trades']} flips · DSR {r['deflated_sharpe_best']}")


if __name__ == "__main__":
    main()
