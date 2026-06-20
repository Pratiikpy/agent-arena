"""Tests for SignalBundle aggregation — the thesis quantities (net_signal × agreement)."""

from __future__ import annotations

from bitarena.domain.market import InstrumentType
from bitarena.perception.base import Signal, SignalBundle, aggregate


def _sig(name: str, value: float, conf: float = 1.0, source: str = "t") -> Signal:
    return Signal(name=name, source=source, value=value, confidence=conf)


def _bundle(*sigs: Signal) -> SignalBundle:
    return SignalBundle(symbol="BTCUSDT", ts=0, signals=tuple(sigs))


def test_net_signal_confidence_weighted_and_zero_weight():
    b = _bundle(_sig("a", 1.0, 1.0), _sig("b", -1.0, 0.0))  # b has zero confidence
    assert b.net_signal == 1.0  # only the confident signal counts
    assert _bundle(_sig("a", 0.5, 0.0), _sig("b", -0.5, 0.0)).net_signal == 0.0  # zero total weight
    assert _bundle().net_signal == 0.0  # no signals


def test_agreement_aligned_split_and_zero():
    assert _bundle(_sig("a", 0.8), _sig("b", 0.6)).agreement == 1.0   # same direction -> unanimous
    assert _bundle(_sig("a", 0.5), _sig("b", -0.5)).agreement == 0.0  # opposite -> perfectly split
    assert _bundle(_sig("a", 0.0), _sig("b", 0.0)).agreement == 0.0   # no conviction -> 0


def test_mean_confidence():
    assert abs(_bundle(_sig("a", 0.5, 0.8), _sig("b", 0.5, 0.4)).mean_confidence - 0.6) < 1e-9
    assert _bundle().mean_confidence == 0.0


def test_by_source_prefix_filter():
    b = _bundle(_sig("a", 0.5, source="agent_hub:macro"), _sig("b", 0.5, source="technical"))
    hub = b.by_source("agent_hub:")
    assert len(hub) == 1 and hub[0].name == "a"


def test_aggregate_collects_from_all_sources():
    class _Src:
        name = "s"

        def observe(self, symbol, market, ts, instrument=InstrumentType.SPOT):
            return [_sig("x", 0.3)]

    bundle = aggregate("BTCUSDT", 0, [_Src(), _Src()], market=None)
    assert len(bundle.signals) == 2 and bundle.symbol == "BTCUSDT"
