"""Trust Score: a transparent, recomputable deserve-capital number, not raw PnL."""

from __future__ import annotations

from bitarena.arena.trust import WEIGHTS, trust_score


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_strong_agent_scores_high():
    t = trust_score({"agent_id": "swarm", "dsr": 0.96, "max_drawdown": -0.02, "total_return": 0.12})
    assert t["grade"] in ("A", "B")
    assert t["trust_score"] >= 0.65
    for v in t["components"].values():
        assert 0.0 <= v <= 1.0


def test_weak_agent_scores_low():
    t = trust_score({"agent_id": "benchmark-buyhold", "dsr": 0.05, "max_drawdown": -0.30, "total_return": -0.10})
    assert t["grade"] == "D"
    assert t["trust_score"] < 0.5
    assert t["components"]["safety"] == 0.0  # a 30% drawdown zeroes the safety component


def test_score_is_the_published_weighted_sum():
    t = trust_score({"agent_id": "regime", "dsr": 0.7, "max_drawdown": -0.05, "total_return": 0.05})
    c = t["components"]
    expected = sum(WEIGHTS[k] * c[k] for k in WEIGHTS)
    assert abs(t["trust_score"] - round(expected, 3)) < 1e-9  # transparent, recomputable


def test_leaderboard_rows_carry_trust():
    from bitarena.arena.leaderboard import build_leaderboard
    from bitarena.arena.portfolio import Portfolio

    pf = Portfolio(agent_id="swarm", starting_cash=10_000.0,
                   equity_curve=[10_000.0, 10_120.0, 10_060.0, 10_200.0])
    rows = build_leaderboard({"swarm": pf})
    assert "trust" in rows[0]
    assert 0.0 <= rows[0]["trust"]["trust_score"] <= 1.0
    assert rows[0]["trust"]["grade"] in ("A", "B", "C", "D")
