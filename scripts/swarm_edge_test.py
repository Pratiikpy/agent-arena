"""Statistical test: does the conflict-gated swarm actually beat naive momentum in chop?

    uv run python scripts/swarm_edge_test.py --scenarios 80

Runs many independent random-walk (choppy) markets, measures swarm-minus-momentum return
per scenario, and reports the mean, win rate, t-stat, and a bootstrap 95% CI. Honest: if
the CI straddles zero, the secondary thesis is not statistically supported.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bitarena.research import swarm_edge_in_chop


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap test of the swarm's edge in chop.")
    parser.add_argument("--scenarios", type=int, default=80)
    parser.add_argument("--out", default="evidence/swarm_edge.json")
    args = parser.parse_args()

    r = swarm_edge_in_chop(n_scenarios=args.scenarios)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(r, indent=2), encoding="utf-8")

    print(f"swarm vs momentum over {r['scenarios']} choppy scenarios ({r['market']}):")
    print(
        f"  mean diff {r['mean_return_diff']*100:+.2f}% | swarm wins {r['swarm_beats_momentum_rate']*100:.0f}% "
        f"| t={r['t_stat']} | 95% CI [{r['ci95'][0]*100:+.2f}%, {r['ci95'][1]*100:+.2f}%] "
        f"| significant={r['significant']}"
    )
    print(f"evidence -> {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
