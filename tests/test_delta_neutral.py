"""Delta-neutral funding carry: a fee-aware, price-hedged yield measured honestly."""

from __future__ import annotations

import numpy as np

from bitarena.research.delta_neutral import carry_pnl, delta_neutral_carry


def _fr(rates):
    return [{"ts": i, "funding_rate": r} for i, r in enumerate(rates)]


def test_steady_funding_earns_positive_gross():
    # steady positive funding, held with almost no flips -> positive gross carry, price-hedged
    rates = np.array([0.0004] * 120)
    out = delta_neutral_carry(_fr(rates), folds=3)
    assert out["best"]["gross_annualized_return"] > 0
    assert out["best"]["trades"] <= 2          # entered once, held (low churn)
    assert out["best"]["time_in_market"] >= 0.8


def test_symmetric_harvests_negative_funding_too():
    # persistently negative funding: the desk flips to short-spot/long-perp and still earns gross
    rates = np.array([-0.0004] * 120)
    out = delta_neutral_carry(_fr(rates), folds=3)
    assert out["best"]["gross_annualized_return"] > 0  # sign-agnostic carry


def test_fees_are_charged_on_side_changes():
    # a clean flip from positive to negative funding costs fees -> net below gross
    rates = np.array([0.001] * 20 + [-0.001] * 20)
    r = carry_pnl(rates, fee_bps_per_leg=6.0, entry_window=4)
    assert r["net"].sum() < r["gross"].sum()  # fees were paid on the flip
    assert r["trades"] >= 2


def test_maker_beats_taker_net():
    # lower (maker) fees leave more of the carry than taker fees
    taker = carry_pnl(np.array([0.0003] * 100), fee_bps_per_leg=6.0, entry_window=30)["net"].sum()
    maker = carry_pnl(np.array([0.0003] * 100), fee_bps_per_leg=1.0, entry_window=30)["net"].sum()
    assert maker > taker


def test_insufficient_history_is_flagged():
    out = delta_neutral_carry(_fr([0.0001, 0.0002]))
    assert out["insufficient"] is True


def test_reports_hedge_gross_and_maker_net():
    out = delta_neutral_carry(_fr(list(np.array([0.0004] * 120))))
    assert "long spot + short perp" in out["hedge"]
    assert out["n_trials"] == 4
    assert "gross_annualized_return" in out["best"]
    assert "net_annualized_maker" in out["best"]
