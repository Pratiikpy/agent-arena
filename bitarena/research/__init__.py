"""Research: edge studies (funding carry, walk-forward, overfit-aware validation)."""

from .arena_walk_forward import default_roster, walk_forward_arena
from .edge_significance import swarm_edge_in_chop
from .funding_carry import carry_returns, equity_curve, study, walk_forward
from .funding_edge import funding_agent_walk_forward

__all__ = [
    "carry_returns",
    "equity_curve",
    "study",
    "walk_forward",
    "walk_forward_arena",
    "default_roster",
    "swarm_edge_in_chop",
    "funding_agent_walk_forward",
]
