"""Overfit Court: deterministic, recomputable verdicts that flag luck before capital moves."""

from __future__ import annotations

from bitarena.arena.court import VERDICTS, build_court, court_verdict


def _row(**kw):
    base = {"agent_id": "swarm", "dsr": 0.5, "profit_factor": 1.3,
            "max_drawdown": -0.03, "trades": 40, "skill_significant": False}
    base.update(kw)
    return base


def test_strong_agent_graduates_to_capital():
    v = court_verdict(_row(dsr=0.97, skill_significant=True), pbo=0.18)
    assert v["verdict"] == "CAPITAL_APPROVED"
    assert all("name" in s and "passed" in s for s in v["stages"])


def test_promising_agent_gets_dust():
    v = court_verdict(_row(dsr=0.6, skill_significant=False), pbo=0.2)
    assert v["verdict"] == "DUST_APPROVED"


def test_high_pbo_is_rejected_as_overfit():
    v = court_verdict(_row(dsr=0.99, skill_significant=True), pbo=0.8)
    assert v["verdict"] == "REJECT_OVERFIT"  # selection luck short-circuits even a high DSR


def test_negative_dsr_is_rejected_as_overfit():
    v = court_verdict(_row(dsr=-0.1), pbo=0.1)
    assert v["verdict"] == "REJECT_OVERFIT"


def test_cost_sensitive_rejection():
    v = court_verdict(_row(profit_factor=0.9), pbo=0.1)
    assert v["verdict"] == "REJECT_COST_SENSITIVE"


def test_deep_drawdown_is_unstable():
    v = court_verdict(_row(profit_factor=1.4, max_drawdown=-0.40), pbo=0.1)
    assert v["verdict"] == "REJECT_UNSTABLE"


def test_thin_track_record_stays_on_paper():
    v = court_verdict(_row(trades=2, dsr=0.99, skill_significant=True), pbo=0.1)
    assert v["verdict"] == "PAPER_ONLY"


def test_build_court_tally_and_sort():
    lb = [_row(agent_id="a", dsr=0.97, skill_significant=True),
          _row(agent_id="b", profit_factor=0.5),
          _row(agent_id="c", trades=2)]
    rep = build_court(lb, {"overfitting": {"pbo": 0.2, "insufficient": False}})
    assert rep["tested"] == 3
    assert rep["rejected"] >= 1 and rep["graduated"] >= 1
    assert sum(rep["tally"].values()) == 3
    # dockets sorted best-verdict first
    idx = [VERDICTS.index(d["verdict"]) for d in rep["dockets"]]
    assert idx == sorted(idx, reverse=True)


def test_signed_report_verifies():
    from bitarena.firewall.signing import Signer, verify_payload

    signer = Signer.load_or_create("./.keys/test_arena.pem")
    rep = build_court([_row(agent_id="a", dsr=0.97, skill_significant=True)],
                      {"overfitting": {"pbo": 0.2, "insufficient": False}}, signer=signer)
    assert verify_payload(rep) is True
    assert rep["dockets"][0]["verdict"] == "CAPITAL_APPROVED"


def test_insufficient_pbo_is_ignored():
    # when the run flags PBO insufficient, it must not trigger an overfit rejection
    v = build_court([_row(agent_id="a", dsr=0.97, skill_significant=True)],
                    {"overfitting": {"pbo": 0.9, "insufficient": True}})
    assert v["run_pbo"] is None
    assert v["dockets"][0]["verdict"] == "CAPITAL_APPROVED"
