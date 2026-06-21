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


def test_mcp_vet_trade_returns_signed_verdict(monkeypatch):
    # Invoke the HEADLINE MCP tool end-to-end. Force the offline synthetic-quote fallback
    # (get_quote -> None) so it needs no network, and confirm it returns a decision plus a
    # certificate that actually verifies.
    pytest.importorskip("mcp")
    import asyncio

    from bitarena.connectors.bitget import BitgetPublicData
    from bitarena.mcp.server import build_server

    monkeypatch.setattr(BitgetPublicData, "get_quote", lambda self, *a, **k: None)
    res = asyncio.run(build_server().call_tool(
        "vet_trade",
        {"symbol": "BTCUSDT", "side": "buy", "notional_usd": 50.0, "instrument": "perp"},
    ))
    blocks = res[0] if isinstance(res, tuple) else res
    structured = res[1] if isinstance(res, tuple) and len(res) > 1 else None
    out = structured if isinstance(structured, dict) and "decision" in structured else json.loads(blocks[0].text)

    assert out["decision"] in ("ALLOW", "ALLOW_CAPPED", "REJECT")
    assert out["certificate"] is not None
    assert out["certificate_valid"] is True  # the signed cert independently verifies


def test_mcp_verify_certificate_tool(monkeypatch):
    # the full trust loop over MCP: vet a trade to get a real signed cert, then verify it via the
    # verify_certificate tool — it must report intact (valid) AND signed by the pinned arena key.
    pytest.importorskip("mcp")
    import asyncio

    from bitarena.connectors.bitget import BitgetPublicData
    from bitarena.mcp.server import build_server

    monkeypatch.setattr(BitgetPublicData, "get_quote", lambda self, *a, **k: None)
    srv = build_server()

    def _out(res, key):
        blocks = res[0] if isinstance(res, tuple) else res
        structured = res[1] if isinstance(res, tuple) and len(res) > 1 else None
        return structured if isinstance(structured, dict) and key in structured else json.loads(blocks[0].text)

    vet = asyncio.run(srv.call_tool(
        "vet_trade", {"symbol": "BTCUSDT", "side": "buy", "notional_usd": 50.0, "instrument": "perp"}))
    cert = _out(vet, "certificate")["certificate"]
    res = asyncio.run(srv.call_tool("verify_certificate", {"certificate": cert}))
    out = _out(res, "valid")
    assert out["valid"] is True and out["trusted"] is True  # intact + signed by the pinned arena key
