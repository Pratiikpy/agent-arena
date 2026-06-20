"""Tests for technical features, Agent Hub adapter, and signal aggregation."""

from __future__ import annotations

import json

import numpy as np

from bitarena.connectors import ReplayMarketData, synthetic_series
from bitarena.perception import (
    AGENT_HUB_SKILLS,
    AgentHubPerception,
    SignalBundle,
    TechnicalPerception,
    aggregate,
    agent_hub_sources,
    rsi,
    sma,
)
from bitarena.perception.base import Signal


def _market(n=150, seed=1):
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=n, seed=seed)})
    md.set_cursor(n - 1)
    return md


def test_sma_and_rsi_bounds():
    x = np.array([1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], dtype=float)
    assert abs(sma(x, 4) - 14.5) < 1e-9
    assert 0.0 <= rsi(x, 14) <= 100.0
    assert rsi(x, 14) > 50  # strictly rising -> high RSI


def test_technical_produces_bounded_signals():
    tech = TechnicalPerception()
    sigs = tech.observe("BTCUSDT", _market(), ts=0)
    names = {s.name for s in sigs}
    assert {"momentum", "trend", "mean_reversion", "rsi"} <= names
    for s in sigs:
        assert -1.0 <= s.value <= 1.0 and 0.0 <= s.confidence <= 1.0


def test_technical_insufficient_history():
    md = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=150, seed=1)})
    md.set_cursor(3)  # only 4 bars visible
    sigs = TechnicalPerception().observe("BTCUSDT", md, ts=0)
    assert len(sigs) == 1 and sigs[0].confidence == 0.0


def test_signal_bundle_agreement_math():
    agree = SignalBundle(
        symbol="X", ts=0,
        signals=(
            Signal(name="a", source="s", value=0.8, confidence=1.0),
            Signal(name="b", source="s", value=0.6, confidence=1.0),
        ),
    )
    assert agree.agreement == 1.0  # same direction
    assert agree.net_signal > 0

    split = SignalBundle(
        symbol="X", ts=0,
        signals=(
            Signal(name="a", source="s", value=0.8, confidence=1.0),
            Signal(name="b", source="s", value=-0.8, confidence=1.0),
        ),
    )
    assert split.agreement == 0.0  # perfectly split
    assert abs(split.net_signal) < 1e-9


def test_agent_hub_fallback_is_labeled():
    src = AgentHubPerception("macro")
    sigs = src.observe("BTCUSDT", _market(), ts=0)
    assert len(sigs) == 1 and "(fallback)" in sigs[0].source


def test_agent_hub_reads_brief(tmp_path):
    (tmp_path / "macro.json").write_text(json.dumps({"score": 0.7, "confidence": 0.9, "summary": "dovish Fed"}))
    src = AgentHubPerception("macro", brief_dir=tmp_path)
    sigs = src.observe("BTCUSDT", _market(), ts=0)
    assert sigs[0].value == 0.7 and sigs[0].confidence == 0.9
    assert sigs[0].source == "agent_hub:macro"  # not a fallback


def test_agent_hub_default_brief_dir_from_env(tmp_path, monkeypatch):
    # The live path is WIRED, not just plumbed: a brief in $BITARENA_BRIEFS_DIR is picked up
    # with NO brief_dir passed (previously brief_dir defaulted to None -> always fallback, so a
    # real Skill brief would never have been used).
    (tmp_path / "sentiment_BTCUSDT.json").write_text(
        json.dumps({"score": -0.4, "confidence": 0.8, "summary": "fear elevated"}))
    monkeypatch.setenv("BITARENA_BRIEFS_DIR", str(tmp_path))
    src = AgentHubPerception("sentiment")  # no brief_dir argument -> resolves the env default
    sigs = src.observe("BTCUSDT", _market(), ts=0)
    assert sigs[0].value == -0.4 and sigs[0].confidence == 0.8
    assert sigs[0].source == "agent_hub:sentiment"  # a live brief, not "(fallback)"


def test_aggregate_all_sources():
    sources = [TechnicalPerception(), *agent_hub_sources()]
    bundle = aggregate("BTCUSDT", 0, sources, _market())
    assert len(AGENT_HUB_SKILLS) == 5
    assert -1.0 <= bundle.net_signal <= 1.0
    assert 0.0 <= bundle.agreement <= 1.0
