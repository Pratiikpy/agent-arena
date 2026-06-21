"""Run the multi-brain model arena on a price path and write evidence/model_arena.json.

Pits the rule brains against a sparse Qwen brain (when a key is present) on identical candle-replay
data, ranked by return with overlaid equity curves. Add another provider key to add an LLM brain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from bitarena.arena.model_arena import LLMBrain, default_rule_brains, run_model_arena
from bitarena.llm import QwenClient


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the multi-brain model arena.")
    ap.add_argument("--out", default="evidence/model_arena.json")
    ap.add_argument("--no-llm", action="store_true", help="rule brains only (skip the model brain)")
    args = ap.parse_args()

    rng = np.random.default_rng(5)
    prices = list(100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, 200))))
    brains = default_rule_brains()
    llm = QwenClient.from_settings()
    if not args.no_llm and llm.available():
        brains.append(LLMBrain("Qwen", llm, every=40))

    res = run_model_arena(prices, brains)
    res["note"] = ("brains trade identical candle-replay data; LLM brains call sparsely and hold on "
                   "failure; add a provider key to enter another LLM brain")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    rank = [f"{b['name']} {b['total_return']:+.1%}" for b in res["brains"]]
    print(f"wrote {args.out}: winner={res['winner']} | {' | '.join(rank)}")


if __name__ == "__main__":
    main()
