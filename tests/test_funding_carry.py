"""Tests for the funding-carry edge study + funding parsing."""

from __future__ import annotations

import numpy as np

from bitarena.connectors.bitget.client import BitgetPublicData
from bitarena.research.funding_carry import carry_returns, equity_curve, study


def test_carry_returns_sign_and_adaptive():
    fr = [0.0001, -0.0002, 0.0003]
    assert list(carry_returns(fr)) == fr  # passive = funding received
    adaptive = carry_returns(fr, adaptive=True, threshold=0.0)
    assert adaptive[1] == 0.0 and adaptive[0] > 0 and adaptive[2] > 0  # negatives skipped


def test_equity_curve_grows_with_positive_returns():
    eq = equity_curve([0.001, 0.001, 0.001])
    assert eq.size == 4 and eq[-1] > eq[0]


def test_study_detects_real_carry():
    rng = np.random.default_rng(0)
    fr = rng.normal(0.0001, 0.00005, 300)  # persistent positive funding (bull-like)
    s = study(fr)
    assert s["passive_carry"]["annualized_return"] > 0
    assert s["deflated_sharpe_best"] is not None
    assert len(s["walk_forward_passive"]) == 4
    assert 0.0 <= s["pct_positive_funding"] <= 1.0


def test_study_no_edge_when_zero_mean():
    rng = np.random.default_rng(1)
    fr = rng.normal(0.0, 0.0001, 300)  # no structural carry
    s = study(fr)
    assert abs(s["passive_carry"]["annualized_return"]) < 0.6  # not a strong edge


def test_parse_funding():
    payload = {
        "code": "00000",
        "data": [
            {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingTime": "1700000000000"},
            {"symbol": "BTCUSDT", "fundingRate": "-0.00005", "fundingTime": "1700028800000"},
        ],
    }
    rows = BitgetPublicData._parse_funding(payload)
    assert len(rows) == 2 and rows[0]["funding_rate"] == 0.0001
    assert BitgetPublicData._parse_funding({"data": []}) == []
