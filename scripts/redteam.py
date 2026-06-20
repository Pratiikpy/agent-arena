"""Run the adversarial red-team battery against the firewall and write signed evidence.

    uv run python scripts/redteam.py

Prints a per-attack table and writes evidence/redteam.json. The headline number is
unsafe_allowed — it must be 0.
"""

from __future__ import annotations

import json
from pathlib import Path

from bitarena.config import load_settings
from bitarena.firewall import Firewall
from bitarena.redteam import run_redteam


def main() -> None:
    firewall = Firewall.with_key(load_settings().signing_key_path)
    report = run_redteam(firewall)

    print(f"{'attack':<28}{'category':<12}{'expected':<10}{'decision':<14}{'safe':<6}blocked_by")
    for r in report["attacks"]:
        print(
            f"{r['name']:<28}{r['category']:<12}{r['expected']:<10}{r['decision']:<14}"
            f"{('yes' if r['handled_safely'] else 'NO'):<6}{r['blocked_by'] or ''}"
        )
    print()
    print(
        f"attacks={report['total_attacks']} (malicious={report['malicious']}, controls={report['controls']})  "
        f"UNSAFE_ALLOWED={report['unsafe_allowed']}  false_rejects={report['false_rejects']}  "
        f"all_signed={report['all_verdicts_signed']}  issuer={report['issuer']}"
    )

    out = Path("evidence/redteam.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"evidence written to: {out.resolve()}")


if __name__ == "__main__":
    main()
