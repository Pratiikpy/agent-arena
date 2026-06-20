"""Run an Agent Arena tournament and write evidence (leaderboard + signed trade logs).

Examples:
    uv run python scripts/run_arena.py --source synthetic --bars 600
    uv run python scripts/run_arena.py --source bitget --symbol BTCUSDT --instrument perp --bars 1000
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.agents import (
    BuyAndHold,
    ConflictGatedSwarm,
    FundingCarryAgent,
    LLMDebateSwarm,
    MomentumBaseline,
    PersonaTeam,
    QLearningAgent,
    RegimeAgent,
)
from bitarena.arena import Arena
from bitarena.config import load_settings
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Firewall


def build_market(source: str, symbol: str, instrument: InstrumentType, bars: int, timeframe: str, seed: int):
    funding: list[dict] = []
    if source == "bitget":
        client = BitgetPublicData()
        try:
            candles = client.get_candles(symbol, instrument, timeframe=timeframe, limit=bars)
            if instrument is InstrumentType.PERP and len(candles) >= 50:
                funding = client.get_funding_history(symbol, limit=400)
        finally:
            client.close()
        if len(candles) >= 50:
            return ReplayMarketData({symbol: candles}), f"bitget:{timeframe}:{len(candles)}bars", funding
        print(f"[warn] only {len(candles)} candles from Bitget — falling back to synthetic")
    series = synthetic_series(symbol, n=bars, seed=seed, drift=0.0008, vol=0.012)
    return ReplayMarketData({symbol: series}), "synthetic", []


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an Agent Arena tournament and write evidence.")
    parser.add_argument("--source", choices=["bitget", "synthetic"], default="synthetic")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", choices=["perp", "spot"], default="perp")
    parser.add_argument("--bars", type=int, default=1000, help="history length to load")
    parser.add_argument("--timeframe", default="1h", help="bar timeframe (agents are tuned for 1h)")
    parser.add_argument("--ticks", type=int, default=None, help="limit number of steps")
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--cash", type=float, default=10_000.0)
    parser.add_argument("--out", default="evidence/last_run")
    parser.add_argument("--with-llm", action="store_true", help="add the Qwen LLM debate agent")
    args = parser.parse_args()

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT
    market, source_label, funding = build_market(args.source, args.symbol, instrument, args.bars, args.timeframe, args.seed)

    settings = load_settings()
    firewall = Firewall.with_key(settings.signing_key_path)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    agents = [
        ConflictGatedSwarm(),
        RegimeAgent(),  # mirrors the published Bitget GetAgent Playbook
        PersonaTeam(),
        QLearningAgent(),
        MomentumBaseline(),
        BuyAndHold(),
    ]
    if funding:  # real perpetual funding available -> enter the carry competitor
        agents.append(FundingCarryAgent(funding))
    if args.with_llm:
        agents.append(LLMDebateSwarm())
    arena = Arena(
        agents=agents,
        exchange=PaperExchange(market),
        market=market,
        symbol=args.symbol,
        firewall=firewall,
        signer=firewall._signer,
        instrument=instrument,
        starting_cash=args.cash,
        ledger_dir=out / "ledgers",
        funding=funding,
    )
    result = arena.run(args.ticks)
    result["source"] = source_label

    (out / "leaderboard.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for agent_id, ledger in arena.ledgers.items():
        ledger.write_csv(out / f"trades_{agent_id}.csv")

    print(f"Arena: {args.symbol} {instrument.value} | source={source_label} | ticks={result['ticks']}")
    print(f"{'rank':<5}{'agent':<20}{'final_equity':>14}{'return':>9}{'sharpe':>11}{'trades':>8}")
    for r in result["leaderboard"]:
        print(
            f"{r['rank']:<5}{r['agent_id']:<20}{r['final_equity']:>14,.2f}"
            f"{(r['total_return'] or 0):>9.3f}{str(r['sharpe']):>11}{r['trades']:>8}"
        )
    fwt = result["firewall"]["totals"]
    print(
        f"firewall: intents={fwt['intents']} allow={fwt['allow']} capped={fwt['allow_capped']} "
        f"reject={fwt['reject']} | ledger_verified={result['ledger_verified']} | "
        f"cross-agent PBO={result['overfitting'].get('pbo')}"
    )
    if result.get("funding_settlements"):
        carry = result["funding_received"].get("funding-carry")
        tail = f" | funding-carry agent carry=${carry:+.2f}" if carry is not None else ""
        print(f"funding: {result['funding_settlements']} settlements applied{tail}")
    print(f"evidence written to: {out.resolve()}")


if __name__ == "__main__":
    main()
