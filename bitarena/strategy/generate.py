"""Generate a ``decide(obs)`` strategy from an English brief via Qwen, with a retry-on-failure loop.

The model is given the exact contract (one ``decide(obs)`` function, the obs keys, the helper
names, the hard bans) and asked for code only. On a validation or smoke-run failure the specific
reason is fed back and it tries again, up to a budget. Returns validated code or raises. With no
model key the caller should fall back to a bundled sample strategy.
"""

from __future__ import annotations

import re

from ..llm import QwenClient
from .sandbox import StrategyError, compile_strategy

_SYS = (
    "You write ONE Python function and nothing else: def decide(obs):. "
    "It returns a float in [-1, 1] (target exposure: +1 full long, -1 full short, 0 flat). "
    "obs is a dict with keys: price (float), prices (list of recent closes, oldest first), "
    "position (current signed exposure), equity (float). "
    "You may ONLY use arithmetic, comparisons, if/return, local variables, and these helpers: "
    "sma(prices,n), ema(prices,n), roc(prices,n), std(prices,n), last(prices), mean(xs), "
    "clip(x,lo,hi), plus len/min/max/abs/round/sum. "
    "NO imports, NO loops, NO comprehensions, NO attribute access, NO other functions or names. "
    "Output ONLY the code, no markdown fences, no prose."
)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


def generate_strategy(brief: str, llm: QwenClient | None = None, *, max_tries: int = 3) -> str:
    """Generate and validate a strategy from ``brief``. Raises StrategyError if it cannot."""
    llm = llm or QwenClient.from_settings()
    if not llm.available():
        raise StrategyError("no model available to generate a strategy")

    msg = f"Strategy brief: {brief}\nWrite decide(obs)."
    last = "no response"
    for _ in range(max_tries):
        raw = llm.chat(_SYS, msg)
        if not raw:
            last = "model returned nothing"
            continue
        code = _strip_fences(raw)
        try:
            compile_strategy(code)  # validate + smoke run
            return code
        except StrategyError as exc:
            last = str(exc)
            msg = (f"Strategy brief: {brief}\nYour previous attempt was rejected: {last}\n"
                   f"Fix exactly that and output decide(obs) only, code only.")
    raise StrategyError(f"could not generate a valid strategy after {max_tries} tries: {last}")
