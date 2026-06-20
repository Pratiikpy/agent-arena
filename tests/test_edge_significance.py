"""Tests for the swarm-edge significance study (structure + determinism)."""

from __future__ import annotations

from bitarena.research import swarm_edge_in_chop


def test_edge_structure_and_bounds():
    r = swarm_edge_in_chop(n_scenarios=10, n=120, boot=300)
    assert r["scenarios"] == 10
    assert 0.0 <= r["swarm_beats_momentum_rate"] <= 1.0
    assert r["ci95"][0] <= r["ci95"][1]
    assert isinstance(r["significant"], bool)
    assert r["significant"] == (r["ci95"][0] > 0)


def test_edge_is_deterministic():
    a = swarm_edge_in_chop(n_scenarios=8, n=120, boot=200)
    b = swarm_edge_in_chop(n_scenarios=8, n=120, boot=200)
    assert a == b
