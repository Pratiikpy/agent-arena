"""Real analyst briefs computed from real market series, loaded in place of the price fallback."""

from __future__ import annotations

import numpy as np

from bitarena.perception.briefs import compute_briefs, write_briefs


def _series(n=80, seed=1):
    rng = np.random.default_rng(seed)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n)))
    vols = rng.uniform(100.0, 200.0, n)
    return list(closes), list(vols)


def test_briefs_cover_all_skills_and_stay_in_range():
    closes, vols = _series()
    briefs = compute_briefs(closes, vols, funding_rate=0.0005)
    assert set(briefs) >= {"technical", "sentiment", "macro", "news", "onchain"}
    for b in briefs.values():
        assert -1.0 <= b["score"] <= 1.0
        assert 0.0 <= b["confidence"] <= 1.0
        assert b["summary"] and b["source"]


def test_positive_funding_reads_contrarian_bearish():
    closes, vols = _series()
    b = compute_briefs(closes, vols, funding_rate=0.001)["sentiment"]  # crowded longs
    assert b["score"] < 0
    assert b["source"] == "bitget-funding"


def test_written_brief_overrides_the_price_fallback(tmp_path):
    from bitarena.perception.agent_hub import AgentHubPerception

    write_briefs(
        {"technical": {"score": 0.42, "confidence": 0.9, "summary": "real read", "source": "bitget-candles"}},
        "BTCUSDT", tmp_path,
    )
    sigs = AgentHubPerception("technical", brief_dir=tmp_path).observe("BTCUSDT", None, 1000)
    assert sigs and abs(sigs[0].value - 0.42) < 1e-9  # the real brief, not the (fallback)
