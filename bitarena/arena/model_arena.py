"""A head-to-head arena where several decision *brains* trade identical candle-replay data, ranked
by return with overlaid equity curves. Every brain sees the same context each step, so only the
reasoning differs (the Nof1 fairness rule). Brains are rule-based or model-backed; the harness takes
any number of model brains, so adding a provider key adds a competitor.

Honesty: with one model key available (Qwen, called sparsely), a run pits that single LLM brain
against rule-based brains. Each brain reports its last reason, so the head-to-head is legible.
"""

from __future__ import annotations

import numpy as np


def _downsample(curve: list[float], points: int = 48) -> list[float]:
    if len(curve) <= points:
        return [round(float(x), 5) for x in curve]
    step = (len(curve) - 1) / (points - 1)
    return [round(float(curve[round(i * step)]), 5) for i in range(points)]


# --- rule brains: pure functions over the prices seen so far, returning (exposure, reason) ---
def _momentum(p: np.ndarray) -> tuple[float, str]:
    if len(p) < 12:
        return 0.0, "warming up"
    roc = p[-1] / p[-11] - 1.0
    return float(np.clip(roc * 12.0, -1, 1)), f"10-bar momentum {roc:+.2%}"


def _mean_reversion(p: np.ndarray) -> tuple[float, str]:
    if len(p) < 20:
        return 0.0, "warming up"
    w = p[-20:]
    sd = float(np.std(w, ddof=1))
    if sd == 0:
        return 0.0, "no dispersion"
    z = (p[-1] - float(np.mean(w))) / sd
    return float(np.clip(-z / 2.0, -1, 1)), f"z-score {z:+.2f}, fading"


def _breakout(p: np.ndarray) -> tuple[float, str]:
    if len(p) < 20:
        return 0.0, "warming up"
    hi, lo = float(np.max(p[-20:])), float(np.min(p[-20:]))
    if p[-1] >= hi:
        return 1.0, "20-bar high, long breakout"
    if p[-1] <= lo:
        return -1.0, "20-bar low, short breakout"
    return 0.0, "inside the range"


def _trend(p: np.ndarray) -> tuple[float, str]:
    if len(p) < 20:
        return 0.0, "warming up"
    fast, slow = float(np.mean(p[-5:])), float(np.mean(p[-20:]))
    return (1.0, "5MA above 20MA") if fast > slow else (-1.0, "5MA below 20MA")


class RuleBrain:
    def __init__(self, name: str, fn) -> None:
        self.name = name
        self.model = "rule"
        self._fn = fn

    def decide(self, prices: list[float]) -> tuple[float, str]:
        return self._fn(np.asarray(prices, dtype=float))


class LLMBrain:
    """A model brain that asks the LLM for a stance sparsely (every ``every`` bars) and holds between.

    On any model failure it holds its last exposure, so a slow or unavailable model never stalls the
    arena. ``model`` is the provider label shown in the ranking.
    """

    def __init__(self, name: str, llm, *, model: str = "qwen", every: int = 25) -> None:
        self.name = name
        self.model = model
        self._llm = llm
        self._every = max(1, every)
        self._calls = 0
        self._exp = 0.0
        self._reason = "no call yet"

    def decide(self, prices: list[float]) -> tuple[float, str]:
        if self._llm is not None and self._llm.available() and (self._calls % self._every == 0):
            p = np.asarray(prices[-30:], dtype=float)
            roc = (p[-1] / p[0] - 1.0) if len(p) > 1 else 0.0
            sys = ("You are a trading model. Given recent price action, reply ONLY as compact JSON "
                   '{"stance":"long|short|flat","conviction":0..1,"reason":"<=12 words"}.')
            user = f"Last {len(p)} closes change {roc:+.2%}, last={p[-1]:.2f}. Decide."
            raw = self._llm.chat(sys, user)
            data = _extract_json(raw or "")
            if data:
                stance = str(data.get("stance", "flat")).lower()
                try:
                    conv = max(0.0, min(1.0, float(data.get("conviction", 0.0))))
                except (TypeError, ValueError):
                    conv = 0.0
                self._exp = conv if stance == "long" else (-conv if stance == "short" else 0.0)
                self._reason = str(data.get("reason", ""))[:80] or f"stance {stance}"
            else:
                self._reason = "model unavailable, holding"
        self._calls += 1
        return self._exp, self._reason


def _extract_json(text: str) -> dict | None:
    import json
    import re
    try:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except (ValueError, AttributeError):
        return None


def default_rule_brains() -> list[RuleBrain]:
    return [
        RuleBrain("Momentum", _momentum),
        RuleBrain("Mean-Reversion", _mean_reversion),
        RuleBrain("Breakout", _breakout),
        RuleBrain("Trend", _trend),
    ]


def run_model_arena(prices: list[float], brains, *, warmup: int = 20, fee_bps: float = 2.0) -> dict:
    """Replay ``prices`` through every brain on identical data; rank by total return."""
    prices = [float(p) for p in prices]
    results = []
    for brain in brains:
        equity, pos, trades = 1.0, 0.0, 0
        curve = [equity]
        last_reason = ""
        for t in range(warmup, len(prices) - 1):
            exp, reason = brain.decide(prices[: t + 1])
            try:
                exp = float(np.clip(float(exp), -1.0, 1.0))
            except (TypeError, ValueError):
                exp = 0.0
            last_reason = reason or last_reason
            if abs(exp - pos) > 1e-9:
                trades += 1
                equity *= 1.0 - (fee_bps / 10_000.0) * abs(exp - pos)
            pos = exp
            equity *= 1.0 + pos * (prices[t + 1] / prices[t] - 1.0)
            curve.append(equity)
        arr = np.asarray(curve, dtype=float)
        rets = np.diff(arr) / arr[:-1]
        sd = float(np.std(rets, ddof=1)) if rets.size > 1 else 0.0
        sharpe = float(np.mean(rets) / sd * np.sqrt(rets.size)) if sd > 0 else 0.0
        results.append({
            "name": brain.name,
            "model": getattr(brain, "model", "rule"),
            "total_return": round(float(arr[-1] - 1.0), 4),
            "sharpe": round(sharpe, 3),
            "trades": trades,
            "last_reason": last_reason,
            "equity_curve": _downsample(curve),
        })
    results.sort(key=lambda r: r["total_return"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
    return {"bars": len(prices), "brains": results, "winner": results[0]["name"] if results else None}
