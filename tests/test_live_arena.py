"""Tests for LiveArena — resumable, idempotent, state-persisting live operation."""

from __future__ import annotations

from bitarena.agents import BuyAndHold, ConflictGatedSwarm, MomentumBaseline, QLearningAgent
from bitarena.arena import LiveArena
from bitarena.connectors import synthetic_series
from bitarena.domain.mandate import default_arena_mandate
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Firewall, Signer


def _live(tmp_path, fw):
    return LiveArena(
        agents=[MomentumBaseline(), BuyAndHold()],
        symbol="BTCUSDT", instrument=InstrumentType.PERP, firewall=fw,
        state_dir=tmp_path, starting_cash=10_000.0,
    )


def test_live_arena_resumes_and_is_idempotent(tmp_path):
    candles = synthetic_series("BTCUSDT", n=60, seed=5, drift=0.001, vol=0.012)
    fw = Firewall(Signer.generate())

    r1 = _live(tmp_path, fw).process(candles[:30])
    assert r1["new_candles"] == 30 and r1["last_ts"] == candles[29].ts
    entries1 = sum(r1["ledger_entries"].values())
    assert r1["ledger_verified"] is True

    # a fresh instance on the same state_dir resumes — only the new candles are processed
    r2 = _live(tmp_path, fw).process(candles[:60])
    assert r2["new_candles"] == 30 and r2["last_ts"] == candles[59].ts
    assert sum(r2["ledger_entries"].values()) >= entries1  # ledger grew, not reset
    assert r2["ledger_verified"] is True

    # re-feeding seen candles is a no-op (idempotent by timestamp)
    r3 = _live(tmp_path, fw).process(candles[:60])
    assert r3["new_candles"] == 0
    assert sum(r3["ledger_entries"].values()) == sum(r2["ledger_entries"].values())


def test_live_arena_persists_portfolio_state(tmp_path):
    candles = synthetic_series("BTCUSDT", n=40, seed=3, drift=0.002, vol=0.01)
    fw = Firewall(Signer.generate())
    _live(tmp_path, fw).process(candles[:20])
    # a fresh instance must load the prior cash/position, not reset to starting cash
    resumed = _live(tmp_path, fw)
    assert resumed.last_ts == candles[19].ts
    assert (tmp_path / "state.json").exists()
    # at least one agent has moved off its starting cash (it traded)
    assert any(pf.cash_usd != 10_000.0 or pf.position_qty != 0.0 for pf in resumed.portfolios.values())


def test_live_arena_accumulates_ticks_and_firewall_stats(tmp_path):
    candles = synthetic_series("BTCUSDT", n=40, seed=8, drift=0.001, vol=0.012)
    fw = Firewall(Signer.generate())

    s1 = _live(tmp_path, fw).process(candles[:20])
    assert s1["ticks"] == 20
    totals1 = s1["firewall"]["totals"]
    assert set(totals1) >= {"intents", "allow", "allow_capped", "reject"}
    assert totals1["intents"] == totals1["allow"] + totals1["allow_capped"] + totals1["reject"] + totals1["exec_fail"]

    # ticks and firewall counters accumulate across resumed runs (not reset)
    s2 = _live(tmp_path, fw).process(candles[:40])
    assert s2["ticks"] == 40
    assert s2["firewall"]["totals"]["intents"] >= totals1["intents"]


def test_qlearn_state_dict_roundtrip():
    import numpy as np

    a = QLearningAgent()
    a._q[(2, 1)] = np.array([0.1, -0.2, 0.3])
    a._q[(0, -1)] = np.array([0.0, 0.5, -0.5])
    b = QLearningAgent()
    b.load_state_dict(a.state_dict())
    assert b.states_seen == 2
    assert b._q[(2, 1)].tolist() == [0.1, -0.2, 0.3]


def test_live_arena_persists_agent_learning(tmp_path):
    candles = synthetic_series("BTCUSDT", n=60, seed=9, drift=0.001, vol=0.013)
    fw = Firewall(Signer.generate())

    def mk():
        return LiveArena(
            agents=[QLearningAgent(), BuyAndHold()], symbol="BTCUSDT",
            instrument=InstrumentType.PERP, firewall=fw, state_dir=tmp_path, starting_cash=10_000.0,
        )

    mk().process(candles[:30])
    resumed = mk()  # loads state -> the RL agent's Q-table is restored, not reset
    assert resumed.agents["rl-qlearn"].states_seen > 0


def test_live_arena_persists_swarm_smoothing(tmp_path):
    # the swarm's conviction EMA must survive restarts, else it resets to 0 each live run
    # (processing ~1 new candle) and stays flat — neutered in live mode.
    candles = synthetic_series("BTCUSDT", n=60, seed=4, drift=0.004, vol=0.008)
    fw = Firewall(Signer.generate())

    def mk():
        return LiveArena(
            agents=[ConflictGatedSwarm(), BuyAndHold()], symbol="BTCUSDT",
            instrument=InstrumentType.PERP, firewall=fw, state_dir=tmp_path, starting_cash=10_000.0,
        )

    first = mk()
    first.process(candles[:40])
    saved = first.agents["swarm"]._conviction_ema
    assert saved != 0.0  # the swarm built up conviction over the window

    resumed = mk()  # loads state -> EMA restored exactly, not reset
    assert resumed.agents["swarm"]._conviction_ema == saved


def test_live_funding_resume_is_timestamp_robust(tmp_path):
    # funding must resume by timestamp: a positionally-shifted (refetched) funding list on
    # a resumed run must not re-apply or skip settlements vs one continuous run.
    candles = synthetic_series("BTCUSDT", n=40, seed=2, drift=0.001, vol=0.01)
    fw = Firewall(Signer.generate())
    f_full = [{"ts": candles[k].ts, "funding_rate": 0.0004} for k in (5, 15, 25, 35)]

    def arena(state, funding):
        return LiveArena(
            agents=[BuyAndHold()], symbol="BTCUSDT", instrument=InstrumentType.PERP,
            firewall=fw, state_dir=tmp_path / state, starting_cash=10_000.0, funding=funding,
        )

    total_one = arena("one", f_full).process(candles)["funding_received"]["benchmark-buyhold"]

    arena("split", f_full).process(candles[:20])
    shifted = [{"ts": candles[0].ts - 10_000, "funding_rate": 0.0004}] + f_full  # positions shift by 1
    total_split = arena("split", shifted).process(candles[:40])["funding_received"]["benchmark-buyhold"]

    assert abs(total_one - total_split) < 1e-4


def test_live_arena_firewall_rejects_orders_outside_mandate(tmp_path):
    # in LIVE mode too, the firewall must reject every order whose symbol isn't in the mandate
    candles = synthetic_series("BTCUSDT", n=50, seed=7, drift=0.004, vol=0.01)
    fw = Firewall(Signer.generate())
    wrong = default_arena_mandate(10_000.0, allowed_symbols=("ETHUSDT",))  # arena trades BTCUSDT
    arena = LiveArena(
        agents=[MomentumBaseline(), ConflictGatedSwarm()], symbol="BTCUSDT",
        instrument=InstrumentType.PERP, firewall=fw, state_dir=tmp_path,
        starting_cash=10_000.0, mandate=wrong,
    )
    totals = arena.process(candles)["firewall"]["totals"]
    assert totals["intents"] > 0                    # agents did propose orders
    assert totals["reject"] == totals["intents"]    # ...and the universe gate rejected every one
    assert totals["allow"] == 0 and totals["allow_capped"] == 0
