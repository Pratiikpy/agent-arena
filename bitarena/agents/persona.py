"""Agent personas: a name, a one-line philosophy, and the single lens each competitor trades by.

The arena's agents are mechanistic decision policies. A persona makes the roster legible
(which agent is which, and *why* it trades the way it does) without touching any decision
logic. The leaderboard, the UI, the MCP roster, the debate transcript, and the trade memo
all read from this one registry, so an agent's identity is defined in exactly one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """A competitor's public identity. Decision logic lives in the agent, not here."""

    agent_id: str
    name: str  # a short, characterful handle
    philosophy: str  # one line: how it decides
    lens: str  # the single market view it trades by


PERSONAS: dict[str, Persona] = {
    "swarm": Persona(
        "swarm",
        "The Consensus",
        "Sizes by how much the signals agree, and stands down when they conflict.",
        "agreement",
    ),
    "regime": Persona(
        "regime",
        "The Regime Switch",
        "Trend-follows a committed trend, fades a range, and stays flat when it is unclear.",
        "market regime",
    ),
    "persona-team": Persona(
        "persona-team",
        "The Committee",
        "A bull, a bear, and a quant vote, and a risk seat vetoes on disagreement.",
        "internal debate",
    ),
    "llm-swarm": Persona(
        "llm-swarm",
        "The Analyst",
        "Reads five analyst desks, argues bull versus bear, and sizes by conviction.",
        "LLM reasoning",
    ),
    "rl-qlearn": Persona(
        "rl-qlearn",
        "The Learner",
        "Trial and error: it reinforces whatever just paid, online and unsupervised.",
        "reinforcement",
    ),
    "baseline-momentum": Persona(
        "baseline-momentum",
        "The Trend Rider",
        "Rides established momentum in one direction with no second-guessing.",
        "momentum",
    ),
    "benchmark-buyhold": Persona(
        "benchmark-buyhold",
        "The Indexer",
        "Buys once and holds, the market's own baseline for everyone else to beat.",
        "buy and hold",
    ),
    "funding-carry": Persona(
        "funding-carry",
        "The Carry Harvester",
        "Takes the side that gets paid funding, harvesting carry rather than direction.",
        "funding carry",
    ),
}


def persona_for(agent_id: str) -> Persona:
    """The persona for an ``agent_id``, or a clean default for an unknown one."""
    p = PERSONAS.get(agent_id)
    if p is not None:
        return p
    pretty = agent_id.replace("-", " ").replace("_", " ").title()
    return Persona(agent_id, pretty, "A competitor in the arena.", "custom")
