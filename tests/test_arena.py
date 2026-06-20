"""End-to-end arena tests: tournament, determinism, firewall constraint, ledger."""

from __future__ import annotations

from bitarena.agents import BuyAndHold, ConflictGatedSwarm, MomentumBaseline
from bitarena.arena import Arena
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.mandate import default_arena_mandate
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Signer


def _arena(seed=1, n=200, mandate=None):
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed, drift=0.003, vol=0.01)}
    md = ReplayMarketData(series)
    agents = [ConflictGatedSwarm(), MomentumBaseline(), BuyAndHold()]
    return Arena(
        agents=agents,
        exchange=PaperExchange(md),
        market=md,
        symbol="BTCUSDT",
        signer=Signer.generate(),
        instrument=InstrumentType.PERP,
        starting_cash=10_000.0,
        mandate=mandate,
    )


def test_tournament_runs_and_reports():
    res = _arena().run()
    assert res["ticks"] > 0
    ids = {r["agent_id"] for r in res["leaderboard"]}
    assert ids == {"swarm", "baseline-momentum", "benchmark-buyhold"}
    assert sorted(r["rank"] for r in res["leaderboard"]) == [1, 2, 3]
    assert res["ledger_verified"] is True
    assert res["firewall"]["totals"]["intents"] > 0


def test_determinism_same_seed():
    a = _arena(seed=5).run()
    b = _arena(seed=5).run()
    fa = {r["agent_id"]: r["final_equity"] for r in a["leaderboard"]}
    fb = {r["agent_id"]: r["final_equity"] for r in b["leaderboard"]}
    assert fa == fb


def test_ledger_entry_count_matches_executions():
    ar = _arena(seed=3)
    res = ar.run()
    totals = res["firewall"]["totals"]
    executed = totals["allow"] + totals["allow_capped"] - totals["exec_fail"]
    assert sum(res["ledger_entries"].values()) == executed


def test_tight_mandate_forces_caps_or_rejects():
    base = default_arena_mandate(10_000.0, allowed_symbols=("BTCUSDT",))
    caps = base.hard_caps.model_copy(
        update={"max_total_exposure_usd": 800.0, "max_order_notional_usd": 800.0}
    )
    tight = base.model_copy(update={"hard_caps": caps})
    res = _arena(seed=2, mandate=tight).run()
    totals = res["firewall"]["totals"]
    assert totals["allow_capped"] + totals["reject"] > 0  # firewall actively constrained sizing


def test_no_single_order_exceeds_order_cap():
    base = default_arena_mandate(10_000.0, allowed_symbols=("BTCUSDT",))
    caps = base.hard_caps.model_copy(update={"max_order_notional_usd": 500.0})
    tight = base.model_copy(update={"hard_caps": caps})
    ar = _arena(seed=4, mandate=tight)
    ar.run()
    for ledger in ar.ledgers.values():
        for record in ledger.records:
            assert record.notional_usd <= 500.0 + 1e-6


def test_arena_requires_at_least_one_agent():
    import pytest

    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=5, seed=1)})
    with pytest.raises(ValueError):
        Arena(agents=[], exchange=PaperExchange(md), market=md, symbol="BTCUSDT")


def test_build_funding_index_skips_malformed_rows():
    idx = Arena._build_funding_index([
        {"ts": 3000, "funding_rate": 0.001},
        {"ts": "bad", "funding_rate": 0.001},  # unparseable ts -> skipped
        {"funding_rate": 0.001},               # missing ts -> skipped
        {"ts": 1000, "funding_rate": 0.002},
    ])
    assert idx == [(1000, 0.002), (3000, 0.001)]  # only valid rows, sorted ascending by ts


def test_arena_settles_funding_into_equity():
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=40, seed=2, drift=0.001, vol=0.005)}
    md = ReplayMarketData(series)
    funding = [{"ts": series["BTCUSDT"][k].ts, "funding_rate": 0.001} for k in (10, 20, 30)]
    ar = Arena(
        agents=[BuyAndHold()], exchange=PaperExchange(md), market=md, symbol="BTCUSDT",
        signer=Signer.generate(), instrument=InstrumentType.PERP, starting_cash=10_000.0, funding=funding,
    )
    res = ar.run()
    assert res["funding_settlements"] == 3
    # a long position paying positive funding loses a little (longs pay shorts when rate > 0)
    assert res["funding_received"]["benchmark-buyhold"] < 0.0


def test_batch_ledgers_are_idempotent_on_rerun(tmp_path):
    # re-running a batch tournament on the same ledger dir must NOT double records (it used to)
    led = tmp_path / "ledgers"
    series = {"BTCUSDT": synthetic_series("BTCUSDT", n=200, seed=1, drift=0.003, vol=0.01)}

    def build():
        md = ReplayMarketData(series)
        return Arena(
            agents=[ConflictGatedSwarm(), MomentumBaseline(), BuyAndHold()],
            exchange=PaperExchange(md), market=md, symbol="BTCUSDT",
            signer=Signer.generate(), instrument=InstrumentType.PERP,
            starting_cash=10_000.0, ledger_dir=led,
        )

    build().run()
    counts1 = {f.name: sum(1 for line in f.open(encoding="utf-8") if line.strip()) for f in led.glob("*.jsonl")}
    build().run()  # second run on the SAME ledger directory
    counts2 = {f.name: sum(1 for line in f.open(encoding="utf-8") if line.strip()) for f in led.glob("*.jsonl")}

    assert counts1 == counts2  # stable across re-runs, not doubled
    assert any(v > 0 for v in counts1.values())  # and at least one agent actually traded
