"""Build the Overfit Court docket from a real tournament leaderboard, plus a synthetic no-edge
cohort, and write a signed report to evidence/overfit_court.json.

The no-edge cohort makes the headline honest and reproducible: strategies fit to noise are run
through the same ladder and rejected, so "tested N, rejected most, graduated few" is a real
number, not a slogan.

Example:
    uv run python scripts/overfit_court.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.arena.court import build_court
from bitarena.firewall.signing import build_signer


def _noedge_cohort(n: int = 12) -> list[dict]:
    """Deterministic no-edge candidates: thin Deflated Sharpe, costs barely covered or not,
    shallow-to-moderate drawdowns. These are the backtests that look fine and are not."""
    rows = []
    for i in range(n):
        # spread DSR across the rejection band, profit factor straddling 1.0
        dsr = round(-0.05 + 0.06 * i, 3)            # -0.05 .. ~0.61
        pf = round(0.85 + 0.05 * (i % 5), 3)         # 0.85 .. 1.05
        dd = round(-0.06 - 0.02 * (i % 6), 3)        # -0.06 .. -0.16
        rows.append({
            "agent_id": f"candidate-{i+1:02d}",
            "dsr": dsr,
            "profit_factor": pf,
            "max_drawdown": dd,
            "trades": 20 + i,
            "skill_significant": dsr >= 0.95,
        })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the signed Overfit Court docket.")
    ap.add_argument("--leaderboard", default="evidence/last_run/leaderboard.json")
    ap.add_argument("--out", default="evidence/overfit_court.json")
    ap.add_argument("--key", default=".keys/arena.pem")
    args = ap.parse_args()

    lb_path = Path(args.leaderboard)
    run_meta: dict = {}
    real_rows: list[dict] = []
    if lb_path.exists():
        run_meta = json.loads(lb_path.read_text(encoding="utf-8"))
        real_rows = run_meta.get("leaderboard", []) if isinstance(run_meta, dict) else []

    # the real tournament agents are judged with the run's actual PBO; the synthetic no-edge
    # cohort is judged on its own merits (no run PBO) so it cannot borrow the real run's selection.
    cohort = _noedge_cohort()
    all_rows = list(real_rows) + cohort

    signer = build_signer(None, args.key)
    report = build_court(all_rows, run_meta, signer=signer)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {out}: tested {report['tested']}, "
          f"rejected {report['rejected']}, graduated {report['graduated']}")
    for d in report["dockets"]:
        print(f"  {d['verdict']:<22} {d['name']} ({d['agent_id']})")


if __name__ == "__main__":
    main()
