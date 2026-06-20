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
