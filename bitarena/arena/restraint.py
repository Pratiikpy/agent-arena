"""Restraint: scoring an agent for what it does not do.

Most trading bots overtrade, and most of their losses come from trades they should never have
placed. An autonomous agent that knows when to stay flat is more fundable than one that fires on
every bar. Raw PnL never captures this; the Restraint Score does.

Three components, weighted and published so the number is recomputable from the run:

- **selectivity (40%)** : how often the agent stayed out. Fewer firewall submissions per bar means
  more abstention. An agent that submits an intent every bar scores 0; one that mostly waits scores high.
- **discipline (30%)** : how cleanly it sized. Orders the firewall had to cap, or rejected outright,
  count against it. An agent whose orders are always within the mandate needs no correction.
- **preservation (30%)** : capital kept, scored from realized max drawdown (the same basis the Trust
  Score uses for safety).

Firewall per-agent stats (``intents``, ``allow_capped``, ``reject``) come straight from the
tournament's ``firewall.by_agent`` block, so nothing new is measured here.
"""

from __future__ import annotations

WEIGHTS = {"selectivity": 0.40, "discipline": 0.30, "preservation": 0.30}


def _c(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def restraint_score(row: dict, fw: dict | None = None) -> dict:
    """Score one agent's restraint from its leaderboard row + firewall stats. Recomputable."""
    fw = fw or {}
    intents = int(fw.get("intents") or 0)
    capped = int(fw.get("allow_capped") or 0)
    rejected = int(fw.get("reject") or 0)
    periods = int(row.get("periods") or 0)

    # selectivity: abstention rate. With no firewall data, stay neutral (0.5) rather than reward.
    if intents and periods:
        selectivity = _c(1.0 - intents / periods)
    elif periods and not intents:
        selectivity = 1.0  # never submitted an order over the whole run
    else:
        selectivity = 0.5

    # discipline: share of submissions that needed no correction (cap) and were never unsafe (reject)
    discipline = _c(1.0 - (capped + rejected) / intents) if intents else 0.5

    dd = abs(float(row.get("max_drawdown", row.get("max_dd", 0.0)) or 0.0))
    preservation = _c(1.0 - dd / 0.25)

    components = {"selectivity": round(selectivity, 3), "discipline": round(discipline, 3),
                 "preservation": round(preservation, 3)}
    score = sum(WEIGHTS[k] * components[k] for k in WEIGHTS)
    return {"restraint_score": round(score, 3), "components": components, "weights": WEIGHTS,
            "abstained": intents == 0 and periods > 0, "submissions": intents}
