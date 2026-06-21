"""English -> a competing arena agent.

Generate a ``decide(obs)`` strategy from a plain-English brief (via Qwen, or a bundled sample when
no key is present), validate it in the AST sandbox, gate it on a backtest, and write the result to
``evidence/nl_strategy.json``. Model output is allowlisted, sandboxed, and backtest-gated before it
could ever trade. Example:
    uv run python scripts/nl_strategy.py --brief "buy strong momentum, short weakness, else flat"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from bitarena.strategy.backtest import admit, backtest
from bitarena.strategy.generate import generate_strategy
from bitarena.strategy.sandbox import StrategyError, compile_strategy

SAMPLE_CODE = '''def decide(obs):
    fast = sma(obs["prices"], 8)
    slow = sma(obs["prices"], 21)
    momentum = roc(obs["prices"], 10)
    if fast > slow and momentum > 0:
        return clip(momentum * 8.0, 0.2, 1.0)
    if fast < slow and momentum < 0:
        return clip(momentum * 8.0, -1.0, -0.2)
    return 0.0
'''


def main() -> None:
    ap = argparse.ArgumentParser(description="Turn an English brief into a validated, backtested strategy.")
    ap.add_argument("--brief", default=("Go long when 10-bar momentum is positive and the short MA is "
                                        "above the long MA; short the mirror case; otherwise stay flat."))
    ap.add_argument("--out", default="evidence/nl_strategy.json")
    args = ap.parse_args()

    source = "qwen"
    try:
        code = generate_strategy(args.brief)
    except StrategyError:
        code, source = SAMPLE_CODE, "sample(no-model)"

    fn = compile_strategy(code)  # validate + smoke (never write code that did not pass the sandbox)
    rng = np.random.default_rng(11)
    prices = list(100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, 180))))
    result = backtest(fn, prices)

    out = {
        "brief": args.brief,
        "source": source,
        "code": code,
        "backtest": result,
        "admitted": admit(result),
        "note": "model output is AST-allowlisted + sandboxed + backtest-gated before it can compete",
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {args.out}: source={source} admitted={out['admitted']} backtest={result}")


if __name__ == "__main__":
    main()
