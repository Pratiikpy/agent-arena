"""Tests for the MCP server's agent roster (reflects the real tournament, not a stub)."""

from __future__ import annotations

import json

import pytest

from bitarena.mcp.server import _FULL_ROSTER, _roster_from_leaderboard


def test_roster_reads_leaderboard(tmp_path):
    (tmp_path / "leaderboard.json").write_text(
        json.dumps({"leaderboard": [{"agent_id": "swarm"}, {"agent_id": "regime"}, {"agent_id": "rl-qlearn"}]}),
        encoding="utf-8",
    )
    assert _roster_from_leaderboard(tmp_path) == ["swarm", "regime", "rl-qlearn"]


def test_roster_fallback_when_missing(tmp_path):
    assert _roster_from_leaderboard(tmp_path) == _FULL_ROSTER
    assert "regime" in _FULL_ROSTER  # the published-Playbook mirror must be in the roster


def test_roster_fallback_on_malformed(tmp_path):
    (tmp_path / "leaderboard.json").write_text("not json", encoding="utf-8")
    assert _roster_from_leaderboard(tmp_path) == _FULL_ROSTER


def test_build_server_smoke():
    pytest.importorskip("mcp")
    from bitarena.mcp.server import build_server

    assert build_server() is not None


def test_mcp_list_agents_tool_invokable():
    # actually invoke a registered MCP tool (list_agents is offline-safe, unlike vet_trade
    # which fetches a live quote) and confirm it returns the roster.
    pytest.importorskip("mcp")
    import asyncio

    from bitarena.mcp.server import build_server

    res = asyncio.run(build_server().call_tool("list_agents", {}))
    # FastMCP returns (content_blocks, structured_result); the structured form holds the list
    blocks = res[0] if isinstance(res, tuple) else res
    structured = res[1] if isinstance(res, tuple) and len(res) > 1 else None
    agents = structured["result"] if structured and "result" in structured else [b.text for b in blocks]
    assert isinstance(agents, list) and len(agents) >= 3
    assert "swarm" in agents
