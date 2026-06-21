"""Generate real analyst briefs from live Bitget data and write them to evidence/briefs/, so the
agents read real signals (real technicals + real funding) instead of the price-trend fallback.

Example:
    uv run python scripts/make_briefs.py --symbol BTCUSDT
"""

from __future__ import annotations

import argparse

from bitarena.connectors import synthetic_series
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain import InstrumentType
from bitarena.perception.briefs import compute_briefs, write_briefs


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate real analyst briefs from Bitget data.")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--out", default="evidence/briefs")
    args = ap.parse_args()

    inst = InstrumentType.PERP
    client = BitgetPublicData()
    candles = client.get_candles(args.symbol, inst, timeframe="1h", limit=160)
    funding = None
    try:
        fh = client.get_funding_history(args.symbol, limit=1)
        funding = float(fh[-1]["funding_rate"]) if fh else None
    except Exception:
        funding = None
    client.close()

    source = "bitget"
    if len(candles) < 60:
        candles = synthetic_series(args.symbol, n=160, seed=1)
        source = "synthetic(fallback)"
    closes = [float(c.close) for c in candles]
    volumes = [float(getattr(c, "volume", 0.0)) for c in candles]

    briefs = compute_briefs(closes, volumes, funding_rate=funding)
    written = write_briefs(briefs, args.symbol, args.out)
    print(f"source={source} funding={funding} symbol={args.symbol}: "
          f"wrote {len(written)} briefs ({', '.join(briefs)})")


if __name__ == "__main__":
    main()
