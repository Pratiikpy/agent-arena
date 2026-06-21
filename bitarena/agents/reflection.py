"""Per-agent reflection memory: record a decision, learn its realized outcome, write a
one-line post-mortem, and condition the next decision on the recent track record.

This is the loop the agentic-trading literature credits with the largest gains: an agent that
reviews its own hits and misses before it acts again. The post-mortem is factual by default
(it cites the realized basis points and whether the call beat the benchmark), with an optional
model-written lesson appended when a model is available, so it never invents a number.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .persona import persona_for


@dataclass
class Decision:
    """One recorded decision and, once the holding window closes, its graded outcome."""

    ts: int
    asset: str
    action: str  # "long" | "short" | "flat"
    thesis: str  # the agent's stated reason at decision time
    pnl_bps: float | None = None  # realized return over the holding window, basis points
    alpha_bps: float | None = None  # realized return minus the buy-hold benchmark, basis points
    reflection: str | None = None  # one-line post-mortem, written once the outcome is known


def _bps(x: float) -> int:
    return int(round(x))


@dataclass
class ReflectionMemory:
    """A small, auditable memory for one agent. No vector store: recency + asset match."""

    agent_id: str
    decisions: list[Decision] = field(default_factory=list)
    path: Path | None = None

    def record(self, *, ts: int, asset: str, action: str, thesis: str) -> Decision:
        """Log a decision at the moment it is made (outcome still unknown)."""
        d = Decision(ts=ts, asset=asset, action=action, thesis=thesis)
        self.decisions.append(d)
        return d

    def resolve(self, decision: Decision, *, pnl_bps: float, alpha_bps: float,
                lesson: str | None = None) -> Decision:
        """Grade a decision once its holding window closes, and write the post-mortem.

        ``lesson`` is an optional model-written sentence; the factual core (the basis points
        and whether the call beat the benchmark) is always derived from the real numbers.
        """
        decision.pnl_bps = float(pnl_bps)
        decision.alpha_bps = float(alpha_bps)
        right = pnl_bps >= 0  # did the position make money; alpha (vs buy-hold) is the stricter bar
        lens = persona_for(self.agent_id).lens
        base = (
            f"{decision.action} {decision.asset}: {_bps(pnl_bps):+d} bps "
            f"(alpha {_bps(alpha_bps):+d}). Call was {'right' if right else 'wrong'}; "
            f"the {lens} read {'held' if right else 'missed'}."
        )
        decision.reflection = f"{base} {lesson.strip()}" if lesson else base
        self._flush()
        return decision

    def recent_context(self, asset: str, k_same: int = 3, k_cross: int = 2) -> str:
        """The recent track record to prepend to the next decision prompt.

        The most recent resolved decisions for this asset, plus a few cross-asset lessons.
        Empty string when there is nothing resolved yet (so it never adds noise on a cold start).
        """
        resolved = [d for d in self.decisions if d.reflection]
        same = [d for d in reversed(resolved) if d.asset == asset][:k_same]
        cross = [d for d in reversed(resolved) if d.asset != asset][:k_cross]
        if not same and not cross:
            return ""
        lines = ["Your recent track record (learn from it):"]
        lines += [f"- {d.reflection}" for d in same]
        if cross:
            lines.append("Cross-asset lessons:")
            lines += [f"- {d.reflection}" for d in cross]
        return "\n".join(lines)

    def hit_rate(self) -> float | None:
        """Share of resolved decisions that beat the benchmark, or ``None`` if none resolved."""
        rs = [d for d in self.decisions if d.alpha_bps is not None]
        if not rs:
            return None
        return round(sum(1 for d in rs if d.alpha_bps >= 0) / len(rs), 3)

    def to_dict(self) -> dict:
        rs = [d for d in self.decisions if d.reflection]
        return {
            "agent_id": self.agent_id,
            "name": persona_for(self.agent_id).name,
            "lens": persona_for(self.agent_id).lens,
            "decisions": [asdict(d) for d in self.decisions],
            "resolved": len(rs),
            "hit_rate": self.hit_rate(),
        }

    def _flush(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
