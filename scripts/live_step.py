"""Advance the live arena by one increment on real Bitget data.

Run this repeatedly (cron, or a deployed worker, e.g. every hour for 1h candles) to drive
a continuously-growing **live** tournament: each run fetches the latest candles, processes
any not yet seen, and persists state + a live leaderboard that the API/UI can serve.

    uv run python scripts/live_step.py --symbol BTCUSDT --instrument perp --state evidence/live

State (portfolios + signed ledgers + cursor + agent learning state) persists under
--state, so the arena resumes across runs — including the Q-learning agent's table, so it
keeps learning continuously rather than restarting each scheduled invocation.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from bitarena.agents import (
    BuyAndHold,
    ConflictGatedSwarm,
    FundingCarryAgent,
    MomentumBaseline,
    PersonaTeam,
    QLearningAgent,
    RegimeAgent,
)
from bitarena.arena import LiveArena
from bitarena.config import load_settings
from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Firewall

_TF_UNITS = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}


def _timeframe_ms(tf: str) -> int:
    try:
        return int(tf[:-1]) * _TF_UNITS[tf[-1].lower()]
    except (ValueError, KeyError, IndexError):
        return 3_600_000  # default to 1h


def main() -> None:
    parser = argparse.ArgumentParser(description="Advance the live arena one increment on real Bitget data.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--instrument", choices=["perp", "spot"], default="perp")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--bars", type=int, default=200, help="recent window to fetch each run")
    parser.add_argument("--state", default="evidence/live")
    parser.add_argument("--cash", type=float, default=10_000.0)
    args = parser.parse_args()

    instrument = InstrumentType.PERP if args.instrument == "perp" else InstrumentType.SPOT
    client = BitgetPublicData()
    candles = client.get_candles(args.symbol, instrument, timeframe=args.timeframe, limit=args.bars)
    # drop the still-forming current bar: Bitget returns the incomplete candle, which would
    # otherwise be processed now and then re-sent with a corrected close next run (and skipped
    # as ts <= last_ts), freezing the most-recent bar's marks. Only ingest closed bars.
    tf_ms = _timeframe_ms(args.timeframe)
    now_ms = int(time.time() * 1000)
    candles = [c for c in candles if c.ts + tf_ms <= now_ms]
    funding = (
        client.get_funding_history(args.symbol, limit=400)
        if instrument is InstrumentType.PERP and len(candles) >= 20
        else []
    )
    client.close()
    if len(candles) < 20:
        print(f"insufficient live data (candles={len(candles)}) — needs network")
        return

    settings = load_settings()
    firewall = Firewall.with_key(settings.signing_key_path)
    roster = [
        ConflictGatedSwarm(), RegimeAgent(), PersonaTeam(), QLearningAgent(), MomentumBaseline(), BuyAndHold(),
    ]
    if funding:
        roster.append(FundingCarryAgent(funding))

    arena = LiveArena(
        agents=roster, symbol=args.symbol, instrument=instrument, firewall=firewall,
        state_dir=args.state, starting_cash=args.cash, funding=funding,
    )
    snap = arena.process(candles)
    snap["source"] = f"bitget:{args.timeframe}:live"
    Path(args.state).mkdir(parents=True, exist_ok=True)
    (Path(args.state) / "leaderboard.json").write_text(json.dumps(snap, indent=2), encoding="utf-8")

    print(f"live arena {args.symbol} {instrument.value}: +{snap['new_candles']} new candles | last_ts={snap['last_ts']}")
    print(f"{'rank':<5}{'agent':<20}{'equity':>13}{'return':>9}{'trades':>8}")
    for r in snap["leaderboard"][:8]:
        print(f"{r['rank']:<5}{r['agent_id']:<20}{r['final_equity']:>13,.2f}{(r['total_return'] or 0):>9.3f}{r['trades']:>8}")
    print(f"ledger_verified={snap['ledger_verified']} | state -> {Path(args.state).resolve()}")


if __name__ == "__main__":
    main()
