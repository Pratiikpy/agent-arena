"""The multi-brain arena: brains trade identical data and are ranked by return."""

from __future__ import annotations

import numpy as np

from bitarena.arena.model_arena import LLMBrain, default_rule_brains, run_model_arena


def _walk(n=160, seed=5):
    rng = np.random.default_rng(seed)
    return list(100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n))))


def test_arena_ranks_brains_on_identical_data():
    res = run_model_arena(_walk(), default_rule_brains())
    assert res["winner"] is not None
    assert len(res["brains"]) == 4
    rets = [b["total_return"] for b in res["brains"]]
    assert rets == sorted(rets, reverse=True)  # ranked by total return, descending
    assert res["brains"][0]["rank"] == 1
    for b in res["brains"]:
        assert b["equity_curve"] and b["last_reason"]


def test_llm_brain_runs_with_a_stub_model():
    class _Stub:
        def available(self):
            return True

        def chat(self, s, u, **k):
            return '{"stance":"long","conviction":0.8,"reason":"uptrend"}'

    res = run_model_arena(_walk(), [LLMBrain("Qwen", _Stub(), every=1)])
    assert res["brains"][0]["model"] == "qwen"
    assert "uptrend" in res["brains"][0]["last_reason"]


def test_arena_reports_bar_count():
    assert run_model_arena(_walk(120), default_rule_brains())["bars"] == 120
