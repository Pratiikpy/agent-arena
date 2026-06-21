"""Agent Passport: the deserve-capital profile assembled per agent."""

from __future__ import annotations

from bitarena.arena.passport import build_all_passports, build_passport


def test_passport_has_the_core_fields():
    row = {"agent_id": "swarm", "dsr": 0.9, "sharpe": 0.5, "total_return": 0.1,
           "max_drawdown": -0.03, "trades": 40, "skill_significant": True,
           "trust": {"trust_score": 0.8, "grade": "A",
                     "components": {"skill": 0.9, "safety": 0.88, "performance": 0.75, "explainability": 0.75}}}
    p = build_passport("swarm", row, {"swarm": 0.31})
    assert p["name"] == "The Consensus"
    assert p["trust_score"] == 0.8 and p["grade"] == "A"
    assert p["capital_allocation"] == 0.31
    assert set(p["limits"]) >= {"max_order_usd", "off_hours_factor"}
    assert p["metrics"]["dsr"] == 0.9
    assert "0 unsafe" in p["red_team"]


def test_all_passports_sorted_by_trust_and_ranked():
    lb = [{"agent_id": "a", "trust": {"trust_score": 0.4, "grade": "D", "components": {}}},
          {"agent_id": "b", "trust": {"trust_score": 0.9, "grade": "A", "components": {}}}]
    ps = build_all_passports(lb)
    assert [p["agent_id"] for p in ps] == ["b", "a"]  # trust descending
    assert ps[0]["rank"] == 1


def test_falls_back_to_full_roster_without_a_leaderboard():
    ps = build_all_passports(None)
    assert len(ps) >= 8  # every persona gets a passport
    ids = {p["agent_id"] for p in ps}
    assert "swarm" in ids and "benchmark-buyhold" in ids


def test_allocator_weights_read_from_history():
    lb = [{"agent_id": "swarm", "trust": {"trust_score": 0.5, "grade": "C", "components": {}}}]
    alloc = {"history": [{"weights": {"swarm": 0.626}}]}
    assert build_all_passports(lb, alloc)[0]["capital_allocation"] == 0.626
