"""MCP server exposing the Agent Arena (vet_trade, get_leaderboard, list_agents)."""

from .server import build_server, main

__all__ = ["build_server", "main"]
