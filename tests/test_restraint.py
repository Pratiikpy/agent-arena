"""Restraint Score: reward the agent for what it does not do. Transparent, recomputable."""

from __future__ import annotations

from bitarena.arena.restraint import WEIGHTS, restraint_score


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_selective_disciplined_agent_scores_high():
    row = {"periods": 1000, "max_drawdown": -0.02}
    fw = {"intents": 50, "allow_capped": 0, "reject": 0}  # rarely trades, never capped/rejected
    r = restraint_score(row, fw)
    assert r["restraint_score"] >= 0.8
    for v in r["components"].values():
        assert 0.0 <= v <= 1.0


def test_overtrader_scores_low():
    row = {"periods": 1000, "max_drawdown": -0.20}
    fw = {"intents": 1000, "allow_capped": 400, "reject": 200}  # fires every bar, often capped/rejected
    r = restraint_score(row, fw)
    assert r["restraint_score"] < 0.4
    assert r["components"]["selectivity"] == 0.0  # submitted on every bar


def test_full_abstainer_flagged():
    r = restraint_score({"periods": 500, "max_drawdown": 0.0}, {"intents": 0})
    assert r["abstained"] is True
    assert r["components"]["selectivity"] == 1.0


def test_score_is_the_published_weighted_sum():
    row = {"periods": 800, "max_drawdown": -0.05}
    fw = {"intents": 200, "allow_capped": 20, "reject": 0}
    r = restraint_score(row, fw)
    c = r["components"]
    expected = sum(WEIGHTS[k] * c[k] for k in WEIGHTS)
    assert abs(r["restraint_score"] - round(expected, 3)) < 1e-9


def test_neutral_without_firewall_data():
    r = restraint_score({"periods": 0}, None)
    assert r["components"]["selectivity"] == 0.5 and r["components"]["discipline"] == 0.5


def test_passport_carries_restraint():
    from bitarena.arena.passport import build_all_passports

    lb = [{"agent_id": "swarm", "periods": 1000, "max_drawdown": -0.02,
           "trust": {"trust_score": 0.7, "grade": "B", "components": {}}}]
    fw = {"swarm": {"intents": 40, "allow_capped": 0, "reject": 0}}
    ps = build_all_passports(lb, None, fw_stats=fw)
    assert "restraint" in ps[0]
    assert ps[0]["restraint"]["restraint_score"] >= 0.8
