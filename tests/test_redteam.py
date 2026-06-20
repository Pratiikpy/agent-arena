"""The firewall must let zero unsafe orders through and not over-block legitimate ones."""

from __future__ import annotations

from bitarena.firewall import Firewall, Signer
from bitarena.redteam import build_attacks, run_redteam


def test_no_unsafe_order_passes():
    report = run_redteam(Firewall(Signer.generate()))
    assert report["unsafe_allowed"] == 0, [a for a in report["attacks"] if not a["handled_safely"]]


def test_legit_controls_are_allowed():
    report = run_redteam(Firewall(Signer.generate()))
    assert report["false_rejects"] == 0


def test_all_verdicts_signed():
    report = run_redteam(Firewall(Signer.generate()))
    assert report["all_verdicts_signed"] is True


def test_battery_covers_every_category():
    cats = {a.category for a in build_attacks()}
    assert {"sizing", "exposure", "leverage", "universe", "instrument", "quote", "rate", "halt", "expiry"} <= cats


def test_each_malicious_attack_handled():
    report = run_redteam(Firewall(Signer.generate()))
    for a in report["attacks"]:
        if a["expected"] in ("reject", "bounded"):
            assert a["handled_safely"], a["name"]
