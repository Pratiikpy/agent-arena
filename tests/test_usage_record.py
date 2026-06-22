"""Usage record: a reproducible, signed firewall-call log (the Track-2 usage artifact)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bitarena.firewall.signing import verify_payload


def _build(tmp_path: Path):
    """Run the script's batch through the firewall into tmp, returning (rows, signed summary)."""
    import runpy
    import os

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        runpy.run_path(str(Path(cwd) / "scripts" / "usage_record.py"), run_name="__main__")
    finally:
        os.chdir(cwd)
    rows = list(csv.DictReader((tmp_path / "evidence" / "usage_record.csv").open(encoding="utf-8")))
    summary = json.loads((tmp_path / "evidence" / "usage_record.json").read_text(encoding="utf-8"))
    return rows, summary


def test_record_has_rows_with_decisions_and_cert_hashes(tmp_path):
    rows, _ = _build(tmp_path)
    assert len(rows) >= 6
    for r in rows:
        assert r["decision"] in ("ALLOW", "ALLOW_CAPPED", "REJECT")
        assert r["cert_hash"]  # every call is bound to a signed certificate


def test_signed_summary_verifies_and_totals_match(tmp_path):
    rows, summary = _build(tmp_path)
    assert verify_payload(summary) is True
    assert summary["calls"] == len(rows)
    assert sum(summary["totals"].values()) == len(rows)
    assert summary["unsafe_passed"] == 0


def test_oversized_capped_and_breach_rejected(tmp_path):
    _, summary = _build(tmp_path)
    assert summary["totals"]["ALLOW_CAPPED"] >= 1  # the 999,999 order was capped, not allowed raw
    assert summary["totals"]["REJECT"] >= 1        # the no-headroom order was rejected
