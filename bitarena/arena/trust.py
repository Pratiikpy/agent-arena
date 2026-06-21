"""Trust Score: one transparent number for whether an agent deserves capital.

Raw PnL ranks agents by outcome. Trust Score ranks them by trustworthiness, blending four
components with the weights stated in the open:

- **skill (40%)** : the Deflated Sharpe Ratio, i.e. does the edge survive an overfit test.
- **safety (30%)** : capital preservation, scored from the realized max drawdown under the firewall.
- **performance (20%)** : realized return, normalized.
- **explainability (10%)** : how much reasoning the agent exposes (signed memos, debate, reason codes).

The formula is never hidden: ``trust_score`` returns the components and the weights so anyone can
recompute it.
"""

from __future__ import annotations

WEIGHTS = {"skill": 0.40, "safety": 0.30, "performance": 0.20, "explainability": 0.10}

# how much reasoning each agent exposes (memos, debate transcripts, reason codes)
_EXPLAIN = {
    "llm-swarm": 0.95, "persona-team": 0.80, "swarm": 0.75, "regime": 0.70,
    "funding-carry": 0.65, "rl-qlearn": 0.60, "baseline-momentum": 0.55,
    "benchmark-buyhold": 0.40,
}


def _c(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _explainability(agent_id: str) -> float:
    return _EXPLAIN.get(agent_id, 0.60)


def _grade(s: float) -> str:
    return "A" if s >= 0.80 else "B" if s >= 0.65 else "C" if s >= 0.50 else "D"


def trust_score(row: dict) -> dict:
    """Compute a Trust Score from a leaderboard row. Returns the score, grade, and components."""
    dsr = row.get("dsr")
    skill = _c(dsr if dsr is not None else 0.0)
    dd = abs(float(row.get("max_drawdown", row.get("max_dd", 0.0)) or 0.0))
    safety = _c(1.0 - dd / 0.25)  # a 25%+ realized drawdown zeroes the safety component
    ret = float(row.get("total_return", 0.0) or 0.0)
    performance = _c((ret + 0.05) / 0.20)  # -5% return -> 0, +15% -> 1
    explainability = _explainability(str(row.get("agent_id", "")))
    components = {"skill": round(skill, 3), "safety": round(safety, 3),
                 "performance": round(performance, 3), "explainability": round(explainability, 3)}
    score = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
    return {"trust_score": round(score, 3), "grade": _grade(score),
            "components": components, "weights": WEIGHTS}
