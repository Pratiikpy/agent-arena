"""The reflection memory loop: record a decision, grade the outcome, learn from it."""

from __future__ import annotations

from bitarena.agents.reflection import ReflectionMemory


def test_record_then_resolve_writes_a_factual_postmortem():
    mem = ReflectionMemory(agent_id="swarm")
    d = mem.record(ts=1, asset="BTC", action="long", thesis="signals agree up")
    assert d.reflection is None  # not graded until the window closes

    mem.resolve(d, pnl_bps=85, alpha_bps=40)
    assert "+85 bps" in d.reflection
    assert "alpha +40" in d.reflection
    assert "right" in d.reflection and "held" in d.reflection


def test_a_losing_call_reads_as_wrong():
    mem = ReflectionMemory(agent_id="regime")
    d = mem.record(ts=1, asset="ETH", action="short", thesis="range fade")
    mem.resolve(d, pnl_bps=-60, alpha_bps=-55)
    assert "wrong" in d.reflection and "missed" in d.reflection
    assert "-60 bps" in d.reflection


def test_optional_lesson_is_appended_factual_core_stays():
    mem = ReflectionMemory(agent_id="llm-swarm")
    d = mem.record(ts=1, asset="BTC", action="long", thesis="x")
    mem.resolve(d, pnl_bps=10, alpha_bps=5, lesson="Size earlier next time.")
    assert d.reflection.endswith("Size earlier next time.")
    assert "+10 bps" in d.reflection  # the model lesson never replaces the real numbers


def test_recent_context_is_empty_on_cold_start_then_populates():
    mem = ReflectionMemory(agent_id="swarm")
    assert mem.recent_context("BTC") == ""  # nothing resolved yet -> no noise

    d1 = mem.record(ts=1, asset="BTC", action="long", thesis="a")
    mem.resolve(d1, pnl_bps=20, alpha_bps=12)
    d2 = mem.record(ts=2, asset="ETH", action="short", thesis="b")
    mem.resolve(d2, pnl_bps=-30, alpha_bps=-18)

    ctx = mem.recent_context("BTC")
    assert "track record" in ctx
    assert "BTC" in ctx and "ETH" in ctx  # same-asset + cross-asset lesson both surface


def test_hit_rate_counts_benchmark_beating_calls():
    mem = ReflectionMemory(agent_id="swarm")
    for alpha in (10, -5, 20):
        d = mem.record(ts=1, asset="BTC", action="long", thesis="x")
        mem.resolve(d, pnl_bps=alpha, alpha_bps=alpha)
    assert mem.hit_rate() == round(2 / 3, 3)


def test_flush_writes_an_auditable_json(tmp_path):
    import json
    path = tmp_path / "reflection.json"
    mem = ReflectionMemory(agent_id="swarm", path=path)
    d = mem.record(ts=1, asset="BTC", action="long", thesis="x")
    mem.resolve(d, pnl_bps=42, alpha_bps=8)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["agent_id"] == "swarm" and data["name"] == "The Consensus"
    assert data["resolved"] == 1 and data["decisions"][0]["reflection"]
