"""Demo the TrustAllocator: does funding agents by verified trust beat equal-weight?

Runs the same fleet on the same market twice — once with a fixed equal split, once with
the adaptive trust allocator — and compares the resulting fund equity. Writes
evidence/allocator.json. Reports honestly whether adaptive trust helped.

    uv run python scripts/allocator_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from bitarena.agents import (
    BuyAndHold,
    ConflictGatedSwarm,
    MomentumBaseline,
    PersonaTeam,
    QLearningAgent,
)
from bitarena.arena import TrustAllocator
from bitarena.config import load_settings
import numpy as np

from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import Candle, InstrumentType
from bitarena.firewall import Firewall


def regime_series(symbol: str, seg: int = 200, seed: int = 7):
    """A trend -> chop -> trend market where agents genuinely diverge."""
    rng = np.random.default_rng(seed)
    price = 100.0
    closes = []
    for _ in range(seg):
        price *= np.exp(rng.normal(0.0015, 0.005))
        closes.append(price)
    level = price
    for _ in range(seg):
        price += (level - price) * 0.05 + rng.normal(0.0, 1.5)
        closes.append(max(1.0, price))
    for _ in range(seg):
        price *= np.exp(rng.normal(0.0015, 0.005))
        closes.append(price)
    candles = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        candles.append(Candle(ts=i * 60_000, open=float(o), high=max(o, c) * 1.001,
                              low=min(o, c) * 0.999, close=float(c), volume=1_000.0))
    return {symbol: candles}, "regime(trend-chop-trend)"


def build_market(source: str, symbol: str, instrument: InstrumentType, bars: int, seed: int):
    if source == "bitget":
        client = BitgetPublicData()
        candles = client.get_candles(symbol, instrument, timeframe="1m", limit=bars)
        client.close()
        if len(candles) >= 50:
            return {symbol: candles}, f"bitget:{len(candles)}bars"
    return {symbol: synthetic_series(symbol, n=bars, seed=seed, drift=0.0008, vol=0.012)}, "synthetic"


def make_agents():
    return [ConflictGatedSwarm(), PersonaTeam(), QLearningAgent(), MomentumBaseline(), BuyAndHold()]


def run(series, symbol, instrument, firewall, *, adaptive):
    market = ReplayMarketData({k: list(v) for k, v in series.items()})
    return TrustAllocator(
        agents=make_agents(),
        exchange=PaperExchange(market),
        market=market,
        symbol=symbol,
        firewall=firewall,
        instrument=instrument,
        pool_usd=50_000.0,
        rebalance_every=50,
        adaptive=adaptive,
    ).run()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="TrustAllocator: adaptive vs equal-weight.")
    parser.add_argument("--source", choices=["bitget", "synthetic"], default="synthetic")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", choices=["perp", "spot"], default="perp")
    parser.add_argument("--bars", type=int, default=600)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--regime", action="store_true", help="use a trend->chop->trend market (agents diverge)")
    parser.add_argument("--out", default="evidence/allocator.json")
    args = parser.parse_args()

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT
    if args.regime:
        series, source = regime_series(args.symbol, seed=args.seed)
    else:
        series, source = build_market(args.source, args.symbol, instrument, args.bars, args.seed)
    firewall = Firewall.with_key(load_settings().signing_key_path)

    equal = run(series, args.symbol, instrument, firewall, adaptive=False)
    adaptive = run(series, args.symbol, instrument, firewall, adaptive=True)

    report = {
        "source": source,
        "symbol": args.symbol,
        "equal_weight": {"fund_final_equity": equal["fund_final_equity"], "fund": equal["fund"]},
        "trust_allocated": {
            "fund_final_equity": adaptive["fund_final_equity"],
            "fund": adaptive["fund"],
            "final_weights": adaptive["final_weights"],
            "rebalances": adaptive["rebalances"],
        },
        "trust_minus_equal_usd": round(adaptive["fund_final_equity"] - equal["fund_final_equity"], 2),
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({**report, "weights_history": adaptive["weights_history"]}, indent=2), encoding="utf-8")

    print(f"source={source}  pool=$50,000")
    print(f"equal-weight fund:     ${equal['fund_final_equity']:,.2f}  (sharpe {equal['fund']['sharpe']})")
    print(f"trust-allocated fund:  ${adaptive['fund_final_equity']:,.2f}  (sharpe {adaptive['fund']['sharpe']})")
    print(f"trust - equal:         ${report['trust_minus_equal_usd']:+,.2f}")
    print("final trust weights:   " + ", ".join(f"{a}={w:.2f}" for a, w in adaptive["final_weights"].items()))
    print(f"evidence written to: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
