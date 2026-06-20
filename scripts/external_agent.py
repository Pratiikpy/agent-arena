"""Drive the reference external agent against a running Agent Arena HTTP API.

Start the API first:  uv run uvicorn bitarena.api.app:app --port 8000
Then:                 uv run python scripts/external_agent.py --source bitget

This is what a third-party developer writes to put Agent Arena's safety firewall in front
of their own bot — a few lines plus one HTTP call per trade.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import InstrumentType
from bitarena.external_example import run_external_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an external bot that vets trades through the firewall API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", choices=["perp", "spot"], default="spot")
    parser.add_argument("--source", choices=["bitget", "synthetic"], default="synthetic")
    parser.add_argument("--steps", type=int, default=120)
    parser.add_argument("--out", default="evidence/external_agent_session.json")
    args = parser.parse_args()

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT
    if args.source == "bitget":
        client = BitgetPublicData()
        candles = client.get_candles(args.symbol, instrument, timeframe="1m", limit=args.steps + 40)
        client.close()
        market = ReplayMarketData({args.symbol: candles}) if len(candles) >= 40 else None
    else:
        market = ReplayMarketData({args.symbol: synthetic_series(args.symbol, n=args.steps + 40, seed=7)})
    if market is None:
        market = ReplayMarketData({args.symbol: synthetic_series(args.symbol, n=args.steps + 40, seed=7)})

    http = httpx.Client(base_url=args.base_url, timeout=10.0)

    def post_firewall(payload: dict) -> dict:
        return http.post("/firewall", json=payload).json()

    try:
        report = run_external_agent(post_firewall, market, symbol=args.symbol, instrument=instrument, steps=args.steps)
    finally:
        http.close()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"external bot on {args.symbol}: decisions={report['decisions']} "
        f"allow={report['allowed']} capped={report['allow_capped']} reject={report['rejected']} "
        f"all_signed={report['all_verdicts_signed']}"
    )
    print(f"evidence written to: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
