"""MCP server exposing the Agent Arena to any MCP client (Claude, Cursor, Codex…).

Tools:
  vet_trade(...)     - run a proposed trade through the firewall; returns a signed verdict
  get_leaderboard()  - the most recent tournament standings
  list_agents()      - the competitor agents available in the arena

Run with:  uv run python -m bitarena.mcp.server   (stdio transport)

The MCP SDK is an optional dependency; install with ``pip install -e ".[mcp]"``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import load_settings
from ..connectors import ReplayMarketData, synthetic_series
from ..connectors.bitget import BitgetPublicData

_FULL_ROSTER = [
    "swarm", "regime", "persona-team", "rl-qlearn",
    "baseline-momentum", "benchmark-buyhold", "funding-carry",
]


def _roster_from_leaderboard(evidence: Path) -> list[str]:
    """Agent ids from the latest tournament leaderboard, or the full-roster fallback."""
    path = evidence / "leaderboard.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = data.get("leaderboard", data) if isinstance(data, dict) else data
            ids = [r["agent_id"] for r in rows if isinstance(r, dict) and r.get("agent_id")]
            if ids:
                return ids
        except (ValueError, KeyError, TypeError):
            pass
    return list(_FULL_ROSTER)


def build_server():
    """Construct the FastMCP server (imports the optional ``mcp`` package lazily)."""
    from mcp.server.fastmcp import FastMCP

    from ..domain import InstrumentType, Side, TradeIntent, default_arena_mandate
    from ..firewall import EvalContext, Firewall, verify_certificate

    settings = load_settings()
    firewall = Firewall.with_key(settings.signing_key_path)
    client = BitgetPublicData()
    evidence = Path("evidence/last_run")
    server = FastMCP("bitarena")

    def quote_for(symbol: str, instrument: InstrumentType):
        live = client.get_quote(symbol, instrument)
        if live is not None:
            return live
        md = ReplayMarketData({symbol: synthetic_series(symbol, n=60, seed=1)})
        md.set_cursor(59)
        return md.get_quote(symbol, instrument)

    @server.tool()
    def vet_trade(
        symbol: str,
        side: str,
        notional_usd: float,
        instrument: str = "spot",
        equity_usd: float = 10_000.0,
        current_exposure_usd: float = 0.0,
    ) -> dict:
        """Vet a proposed trade through the Agent Arena firewall.

        Returns an ALLOW / ALLOW_CAPPED / REJECT decision and an Ed25519-signed
        certificate that can be verified offline with the embedded public key.
        """
        inst = InstrumentType.PERP if instrument == "perp" else (
            InstrumentType.TOKENIZED_EQUITY if instrument == "tokenized_equity" else InstrumentType.SPOT
        )
        intent = TradeIntent(
            agent_id="mcp-client",
            symbol=symbol,
            side=Side(side),
            instrument=inst,
            notional_usd=notional_usd,
        )
        quote = quote_for(symbol, inst)
        mandate = default_arena_mandate(equity_usd, allowed_symbols=(symbol.upper(),))
        ctx = EvalContext(
            mandate=mandate,
            equity_usd=equity_usd,
            quote=quote,
            current_exposure_usd=current_exposure_usd,
            now_ms=quote.ts if quote else None,
            max_quote_age_ms=10 ** 15,
        )
        verdict = firewall.evaluate(intent, ctx)
        return {
            "decision": verdict.decision.value,
            "reason": verdict.reason,
            "effective_notional_usd": verdict.effective_notional_usd,
            "certificate": verdict.certificate.model_dump() if verdict.certificate else None,
            "certificate_valid": verify_certificate(verdict.certificate) if verdict.certificate else None,
        }

    @server.tool()
    def get_leaderboard() -> dict:
        """Return the most recent Agent Arena tournament standings."""
        path = evidence / "leaderboard.json"
        if not path.exists():
            return {"detail": "no tournament run yet"}
        return json.loads(path.read_text(encoding="utf-8"))

    @server.tool()
    def list_agents() -> list[str]:
        """List the competitor agents in the arena (from the latest tournament)."""
        return _roster_from_leaderboard(evidence)

    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
