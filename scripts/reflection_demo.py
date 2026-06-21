"""Reflection-memory demo: an agent records each decision, learns its realized outcome, writes a
one-line post-mortem, and so can quote its own recent track record before the next decision.

Drives a momentum policy over a deterministic price path, grades each decision after a fixed
holding window against the real price move (and against buy-hold), and writes the auditable
memory to ``evidence/reflection.json``. Every number is computed from the path, never invented.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from bitarena.agents.reflection import ReflectionMemory

OUT = Path("evidence/reflection.json")
AGENT = "baseline-momentum"
HOLD = 6  # bars held per decision before it is graded
N = 120


def main() -> None:
    rng = np.random.default_rng(7)  # deterministic path
    steps = rng.normal(0.0008, 0.02, N)  # mild upward drift + noise
    price = 60_000.0 * np.exp(np.cumsum(steps))

    mem = ReflectionMemory(agent_id=AGENT, path=OUT)
    for t in range(20, N - HOLD, HOLD):
        ma_fast = price[t - 5:t].mean()
        ma_slow = price[t - 20:t].mean()
        if ma_fast > ma_slow * 1.002:
            action, sign = "long", 1
        elif ma_fast < ma_slow * 0.998:
            action, sign = "short", -1
        else:
            action, sign = "flat", 0
        thesis = f"5/20 MA {'up' if sign > 0 else 'down' if sign < 0 else 'flat'} cross"
        d = mem.record(ts=int(t), asset="BTC", action=action, thesis=thesis)
        chg_bps = (price[t + HOLD] / price[t] - 1.0) * 10_000.0
        pnl_bps = sign * chg_bps
        alpha_bps = pnl_bps - chg_bps  # versus buy-holding the asset over the same window
        mem.resolve(d, pnl_bps=pnl_bps, alpha_bps=alpha_bps)

    d = mem.to_dict()
    print(f"wrote {OUT}: {d['resolved']} graded decisions, hit_rate={d['hit_rate']}")
    print("--- the context the next BTC decision would see ---")
    print(mem.recent_context("BTC"))


if __name__ == "__main__":
    main()
