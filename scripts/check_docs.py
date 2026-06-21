"""Guard against stale numbers drifting into the docs.

Cross-checks every number cited in the Markdown docs against the source of truth — the live
test count (``pytest --collect-only``), the red-team battery (``evidence/redteam.json``), and
the firewall benchmark (``evidence/firewall_bench.json``). Exits non-zero on any mismatch, so
CI fails the moment a doc claims "20 attacks" while the battery has 23, or a stale test count.

    uv run python scripts/check_docs.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [
    "README.md", "SUBMISSION.md", "SUBMISSION_PACKET.md", "PITCH.md",
    "SELF_ASSESSMENT.md", "DEMO.md", "evidence/README.md", "playbook/PUBLISHED.md",
]

for _stream in (sys.stdout, sys.stderr):  # tolerate a cp1252 console
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass


def _test_count() -> int:
    out = subprocess.run(
        ["uv", "run", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout
    counts = [int(m) for m in re.findall(r":\s*(\d+)\s*$", out, re.M)]
    return sum(counts)


def main() -> int:
    rt = json.loads((ROOT / "evidence/redteam.json").read_text(encoding="utf-8"))
    bench = json.loads((ROOT / "evidence/firewall_bench.json").read_text(encoding="utf-8"))
    tests = _test_count()
    tput = round(bench["throughput_per_sec"] / 100) * 100  # nearest 100

    # (regex, label, expected, tolerance)
    checks = [
        (r"(\d+)\s+(?:passing|tests)", "test count", tests, 0),
        (r"(\d+)-case", "red-team total", rt["total_attacks"], 0),
        (r"(\d+)\s+(?:adversarial\s+)?attacks", "red-team attacks", rt["malicious"], 0),
        (r"(\d+)\s+controls", "red-team controls", rt["controls"], 0),
        (r"~?([\d,]+)\s*(?:verdicts)?\s*/\s*sec", "throughput", tput, 100),
    ]

    problems: list[str] = []
    for rel in DOCS:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for pattern, label, expected, tol in checks:
            for raw in re.findall(pattern, text):
                n = int(str(raw).replace(",", ""))
                if abs(n - expected) > tol:
                    problems.append(f"{rel}: {label} cites {n}, expected {expected}")

    # Headline deterministic-evidence figures aren't covered by the regexes above (each appears
    # once, in a specific phrasing). Guard them as present-string checks: the value formatted from
    # its evidence file must appear verbatim somewhere in the docs, so a regenerated value can't
    # silently drift from what the docs claim.
    fv = json.loads((ROOT / "evidence/firewall_value.json").read_text(encoding="utf-8"))
    ks = json.loads((ROOT / "evidence/regime_killswitch.json").read_text(encoding="utf-8"))
    ot = json.loads((ROOT / "evidence/overfit_trap.json").read_text(encoding="utf-8"))
    # Money-maker figures: the returns/PF the docs lead with must trace to the committed evidence,
    # so a regenerated backtest or a typo can't drift the headline profit claims. Playbook numbers
    # are fixed on-platform backtests; the funding yield is derived from the committed carry study.
    pb = json.loads((ROOT / "evidence/playbook_backtests.json").read_text(encoding="utf-8"))
    fc = json.loads((ROOT / "evidence/funding_carry.json").read_text(encoding="utf-8"))
    top_pb = next(p for p in pb["published"] if p["name"] == "momentum-breakout-btc")
    pfs = [p["profit_factor"] for p in pb["published"]]
    fc_btc_adaptive = max(
        fc["symbols"]["BTCUSDT"]["adaptive_sweep"], key=lambda x: x["sharpe_annualized"]
    )
    # signed-ledger totals, computed from the evidence the verifier checks (matches
    # verify_evidence.py's "N files, M signed records") — guards the "verify in 60 seconds" count.
    ledger_files = sorted((ROOT / "evidence").glob("*/ledgers/*.jsonl"))
    ledger_records = sum(
        1 for f in ledger_files for line in f.read_text(encoding="utf-8").splitlines() if line.strip()
    )
    combined = "\n".join(
        (ROOT / rel).read_text(encoding="utf-8") for rel in DOCS if (ROOT / rel).exists()
    )
    present = [
        (f"${round(fv['firewall_saved_usd']):,}", "firewall containment value"),
        (f"${round(ks['loss_avoided_usd']):,}", "kill-switch loss avoided"),
        (f"PBO {ot['cross_agent_pbo']:.2f}", "overfit-trap PBO"),
        (f"{ledger_records:,} ", "signed-record count"),  # trailing space: matches "8,414 records"/"8,414 signed records"
        (f"{len(ledger_files)} ledgers", "ledger file count"),
        # money-maker figures (rank-7 guard): every headline return the docs cite must match evidence
        (f"{top_pb['profit_factor']:.2f}", "top-Playbook profit factor"),            # 2.33
        (f"{top_pb['budget_return_pct']:.1f}%", "top-Playbook budget return"),        # 39.7%
        (f"{top_pb['budget_return_pct'] / 100:.2f}%", "top-Playbook account return"), # 0.40%
        (f"{top_pb['max_drawdown_pct']:.2f}%", "top-Playbook drawdown"),              # 0.26%
        (f"{min(pfs):.2f}", "lowest published profit factor"),                        # 1.42
        (f"{max(pfs):.2f}", "highest published profit factor"),                       # 3.34
        (f"{fc_btc_adaptive['annualized_return'] * 100:.1f}%", "funding-carry yield"),# 3.1%
    ]
    for token, label in present:
        if token not in combined:
            problems.append(f"{label}: evidence shows '{token}' but no doc cites it (stale?)")

    if problems:
        print("✗ doc number mismatches:")
        for x in problems:
            print("  -", x)
        return 1
    print(
        f"✓ docs consistent — {tests} tests, red-team {rt['malicious']}+{rt['controls']}="
        f"{rt['total_attacks']} (0 unsafe), ~{tput:,}/sec"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
