"""End-to-end property test: the full arena pipeline must survive degenerate markets.

The arena can be pointed at any Bitget symbol — illiquid/flat tapes, slow drifts, pure
chop, or a data-glitch spike. Over all of them the whole loop (perception -> agents ->
firewall -> exchange -> portfolio -> ledger) must complete without crashing, keep every
equity finite, and leave the signed ledger verifiable.
"""

from __future__ import annotations

import math
import random

from bitarena.arena import Arena
from bitarena.connectors import PaperExchange, ReplayMarketData
from bitarena.domain.market import Candle, InstrumentType
from bitarena.firewall import Firewall, Signer
from bitarena.research import default_roster


def _candles(rng: random.Random, kind: str, n: int) -> list[Candle]:
    base = rng.uniform(50.0, 60_000.0)
    closes = []
    for i in range(n):
        if kind == "flat":
            c = base
        elif kind == "drift":
            c = base * (1.0 + 0.0005 * i)
        elif kind == "chop":
            c = base * (1.0 + 0.01 * (1 if i % 2 else -1))
        else:  # "spike" — a single 50x data-glitch bar in the middle
            c = base * (50.0 if i == n // 2 else 1.0)
        closes.append(max(1e-6, c))
    out = []
    for i, c in enumerate(closes):
        out.append(Candle(
            ts=1_700_000_000_000 + i * 60_000,
            open=closes[i - 1] if i else c,
            high=c * 1.001, low=c * 0.999, close=c, volume=rng.uniform(0.0, 1_000.0),
        ))
    return out


def test_arena_survives_degenerate_markets():
    rng = random.Random(3)
    for _ in range(20):
        kind = rng.choice(["flat", "drift", "chop", "spike"])
        n = rng.choice([25, 60, 150, 240])
        md = ReplayMarketData({"BTCUSDT": _candles(rng, kind, n)})
        arena = Arena(
            agents=default_roster(),
            exchange=PaperExchange(md),
            market=md,
            symbol="BTCUSDT",
            firewall=Firewall(Signer.generate()),
            instrument=InstrumentType.PERP,
            starting_cash=10_000.0,
        )
        res = arena.run()
        assert res["ledger_verified"] is True
        assert res["leaderboard"]
        for row in res["leaderboard"]:
            assert math.isfinite(row["final_equity"]), f"non-finite equity on {kind}/{n}"
            assert row["total_return"] is None or math.isfinite(row["total_return"])
            assert math.isfinite(row.get("sharpe") or 0.0)


def test_arena_applies_funding_to_held_positions():
    from bitarena.agents import BuyAndHold

    n = 60
    candles = _candles(random.Random(1), "drift", n)  # rising -> BuyAndHold holds a long
    funding = [{"ts": candles[n // 2].ts, "funding_rate": 0.001}]  # one positive settlement mid-run
    md = ReplayMarketData({"BTCUSDT": candles})
    arena = Arena(
        agents=[BuyAndHold()], exchange=PaperExchange(md), market=md, symbol="BTCUSDT",
        firewall=Firewall(Signer.generate()), instrument=InstrumentType.PERP,
        starting_cash=10_000.0, funding=funding,
    )
    res = arena.run()
    assert res["funding_settlements"] == 1
    assert res["funding_received"]["benchmark-buyhold"] < 0  # a long pays positive funding
    assert res["ledger_verified"] is True


def test_arena_without_funding_is_unaffected():
    candles = _candles(random.Random(2), "drift", 40)
    md = ReplayMarketData({"BTCUSDT": candles})
    from bitarena.agents import BuyAndHold

    res = Arena(
        agents=[BuyAndHold()], exchange=PaperExchange(md), market=md, symbol="BTCUSDT",
        firewall=Firewall(Signer.generate()), instrument=InstrumentType.PERP, starting_cash=10_000.0,
    ).run()
    assert res["funding_settlements"] == 0
    assert res["funding_received"]["benchmark-buyhold"] == 0.0
