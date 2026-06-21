"""Competitor trading agents."""

from .base import AgentObservation, TradingAgent, rebalance_to_target
from .baseline import BuyAndHold, MomentumBaseline
from .funding import FundingCarryAgent
from .llm_swarm import LLMDebateSwarm
from .nl_strategy import NLStrategyAgent
from .personas import PersonaTeam
from .regime import RegimeAgent
from .rl import QLearningAgent
from .swarm import ConflictGatedSwarm

__all__ = [
    "AgentObservation",
    "TradingAgent",
    "rebalance_to_target",
    "MomentumBaseline",
    "BuyAndHold",
    "ConflictGatedSwarm",
    "LLMDebateSwarm",
    "NLStrategyAgent",
    "PersonaTeam",
    "QLearningAgent",
    "RegimeAgent",
    "FundingCarryAgent",
]
