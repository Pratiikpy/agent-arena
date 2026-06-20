"""Tests for the TrustAllocator meta-agent and its weighting math."""

from __future__ import annotations


from bitarena.agents import BuyAndHold, ConflictGatedSwarm, MomentumBaseline, PersonaTeam
from bitarena.arena import TrustAllocator, rolling_score, trust_weights
from bitarena.connectors import PaperExchange, ReplayMarketData, synthetic_series
from bitarena.domain.market import InstrumentType
from bitarena.firewall import Signer, Firewall


def test_rolling_score_sign():
    rising = [100, 102, 104, 106, 108]
    falling = [100, 98, 95, 92, 90]
    assert rolling_score(rising, 10) > 0
    assert rolling_score(falling, 10) < 0


def test_trust_weights_sum_to_one_and_favor_best():
    w = trust_weights([0.10, 0.02, -0.01])
    assert abs(w.sum() - 1.0) < 1e-9
    assert w[0] == max(w)  # best score gets the most


def test_trust_weights_starve_bad_agent():
    # one agent deeply negative -> starved to zero
    w = trust_weights([0.10, 0.05, -0.50], starve_below=-0.05)
    assert w[2] == 0.0
    assert abs(w.sum() - 1.0) < 1e-9


def _market(seed=11, n=400):
    return ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed, drift=0.0008, vol=0.012)})


def _alloc(market, *, adaptive=True, firewall=None, state_path=None):
    return TrustAllocator(
        agents=[ConflictGatedSwarm(), PersonaTeam(), MomentumBaseline(), BuyAndHold()],
        exchange=PaperExchange(market),
        market=market,
        symbol="BTCUSDT",
        firewall=firewall or Firewall(Signer.generate()),
        instrument=InstrumentType.PERP,
        pool_usd=40_000.0,
        rebalance_every=50,
        adaptive=adaptive,
        state_path=state_path,
    )


def test_allocator_runs_and_reports():
    res = _alloc(_market()).run()
    assert res["ticks"] > 0
    assert abs(sum(res["final_weights"].values()) - 1.0) < 1e-6
    assert res["rebalances"] > 0
    assert res["fund"]["periods"] > 0


def test_equal_weight_has_no_rebalances():
    res = _alloc(_market(), adaptive=False).run()
    assert res["rebalances"] == 0
    # equal weights preserved
    assert all(abs(w - 0.25) < 1e-9 for w in res["final_weights"].values())


def test_allocator_deterministic():
    a = _alloc(_market(seed=5)).run()
    b = _alloc(_market(seed=5)).run()
    assert a["fund_final_equity"] == b["fund_final_equity"]
    assert a["final_weights"] == b["final_weights"]


def test_weights_persist_across_runs(tmp_path):
    path = tmp_path / "trust.json"
    first = _alloc(_market(seed=7), state_path=path)
    first.run()
    assert path.exists()
    # a fresh allocator loads the prior run's persisted weights at init (trust compounds)
    fresh = _alloc(_market(seed=7), state_path=path)
    for aid in first.weights:
        assert abs(fresh.weights[aid] - first.weights[aid]) < 1e-6


def test_rolling_score_degenerate():
    assert rolling_score([100.0], 10) == 0.0              # too few points
    assert rolling_score([0.0, 100.0, 110.0], 10) == 0.0  # non-positive starting equity


def test_trust_weights_all_below_line_nobody_starved():
    # if every agent is below the starve line, nobody is starved — the fund stays invested
    w = trust_weights([-0.10, -0.20, -0.30], starve_below=-0.05)
    assert abs(w.sum() - 1.0) < 1e-9
    assert (w > 0).all()


def test_allocator_requires_at_least_one_agent():
    import pytest

    m = _market(n=5)
    with pytest.raises(ValueError):
        TrustAllocator(agents=[], exchange=PaperExchange(m), market=m, symbol="BTCUSDT")


def test_allocator_recovers_from_corrupt_state(tmp_path):
    path = tmp_path / "trust.json"
    path.write_text("{not valid json", encoding="utf-8")  # corrupt -> _load_state must swallow it
    alloc = _alloc(_market(seed=7), state_path=path)
    assert abs(sum(alloc.weights.values()) - 1.0) < 1e-9  # falls back to valid equal weights
