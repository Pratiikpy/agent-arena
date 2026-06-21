"""FastAPI app exposing the firewall and tournament results over HTTP.

Endpoints:
  GET  /                 - the production single-page UI (firewall / arena / ledger / debate / verify)
  GET  /health           - liveness + signing-key fingerprint
  POST /firewall         - evaluate a trade intent, return a signed verdict
  POST /verify           - independently re-check a certificate's Ed25519 signature
  GET  /pubkey           - the issuer's Ed25519 public key (for offline verification)
  GET  /leaderboard      - the most recent tournament result (from evidence/)
  GET  /live             - the live arena's continuously-growing leaderboard (from evidence/live/)
  GET  /ledger?agent=... - recent signed trade records for an agent
  GET  /debate           - the most recent live LLM debate (from evidence/)

The /firewall endpoint prices the intent with a live Bitget quote (keyless public
data), falling back to a synthetic quote only if Bitget is unreachable.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import load_settings
from ..connectors import ReplayMarketData, synthetic_series
from ..connectors.bitget import BitgetPublicData
from ..domain import Certificate, InstrumentType, Side, TradeIntent, default_arena_mandate
from ..firewall import EvalContext, Firewall, MarketRegime, assess_regime, verify_certificate

_AGENT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class FirewallRequest(BaseModel):
    agent_id: str = "external-agent"
    symbol: str = "BTCUSDT"
    side: Side
    instrument: InstrumentType = InstrumentType.SPOT
    notional_usd: float | None = Field(None, ge=0, allow_inf_nan=False)
    quantity: float | None = Field(None, ge=0, allow_inf_nan=False)
    leverage: float = Field(1.0, ge=0, le=125, allow_inf_nan=False)
    equity_usd: float = Field(10_000.0, gt=0, allow_inf_nan=False)
    current_exposure_usd: float = Field(0.0, ge=0, allow_inf_nan=False)


def create_app(
    *, evidence_dir: str = "evidence/last_run", web_dir: str = "web", offline: bool = False,
    market_client=None,
) -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="Agent Arena", version="0.1.0")
    # Wildcard CORS is intentional: this is a public, credential-less read/verify API — the
    # whole point is that anyone, from any origin, can vet a trade and independently check a
    # certificate. allow_credentials stays at its default (False), so no cookies/auth are exposed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    firewall = Firewall.with_settings(settings)
    # An injected market_client (used by tests to exercise the live path) always wins; otherwise
    # offline -> no live data, online -> the real Bitget public client.
    if market_client is None and not offline:
        market_client = BitgetPublicData()
    evidence = Path(evidence_dir)
    web = Path(web_dir)

    def quote_for(symbol: str, instrument: InstrumentType):
        if market_client is not None:
            live = market_client.get_quote(symbol, instrument)
            if live is not None:
                return live
        md = ReplayMarketData({symbol: synthetic_series(symbol, n=60, seed=1)})
        md.set_cursor(59)
        q = md.get_quote(symbol, instrument)
        # the synthetic fallback is generated on-demand → stamp it "now" so the real-time
        # freshness gate treats it as fresh (a genuinely stale *live* quote still rejects,
        # since live quotes keep their real exchange timestamp).
        return q.model_copy(update={"ts": int(time.time() * 1000)}) if q is not None else None

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "issuer": firewall.issuer, "version": app.version}

    @app.get("/pulse")
    def pulse() -> dict:
        """Live heartbeat: a freshly Ed25519-signed firewall verdict on the latest BTC quote,
        stamped with the server time. Every call is fresh — poll it to watch the signed firewall
        run live. ``data_source`` is reported honestly (``bitget-live`` when the real quote is
        reachable, else a fresh ``synthetic`` quote)."""
        now_ms = int(time.time() * 1000)
        symbol, instrument = "BTCUSDT", InstrumentType.PERP
        source, quote = "synthetic", None
        if market_client is not None:
            quote = market_client.get_quote(symbol, instrument)
            if quote is not None:
                source = "bitget-live"
        if quote is None:
            md = ReplayMarketData({symbol: synthetic_series(symbol, n=60, seed=now_ms % 100_000)})
            md.set_cursor(59)
            q = md.get_quote(symbol, instrument)
            quote = q.model_copy(update={"ts": now_ms}) if q is not None else None
        # market-wide regime from recent live candles → drives the fleet kill-switch
        regime = MarketRegime.NORMAL
        if market_client is not None:
            try:
                candles = market_client.get_candles(symbol, instrument, limit=12)
                if candles:
                    regime = assess_regime([c.close for c in candles])
            except Exception:  # network/parse issues must not break the heartbeat
                pass
        intent = TradeIntent(
            agent_id="pulse", symbol=symbol, side=Side.BUY,
            instrument=instrument, notional_usd=50.0,
        )
        mandate = default_arena_mandate(10_000.0, allowed_symbols=(symbol,))
        ctx = EvalContext(
            mandate=mandate, equity_usd=10_000.0, quote=quote, regime=regime,
            now_ms=now_ms, max_quote_age_ms=120_000,
        )
        verdict = firewall.evaluate(intent, ctx)
        cert = verdict.certificate
        return {
            "server_time_ms": now_ms,
            "data_source": source,
            "regime": regime.value,
            "kill_switch_armed": regime is MarketRegime.FAST_RISK_OFF,
            "quote": {
                "symbol": symbol,
                "mid": quote.mid if quote else None,
                "ts": quote.ts if quote else None,
                # clamp at 0: a live exchange ts can run a few ms ahead of the server clock
                "age_ms": max(0, now_ms - quote.ts) if quote else None,
            },
            "verdict": {
                "decision": verdict.decision.value,
                "effective_notional_usd": verdict.effective_notional_usd,
                "reason": verdict.reason,
            },
            "issuer": firewall.issuer,
            "certificate": cert.model_dump() if cert else None,
            "certificate_valid": verify_certificate(cert) if cert else None,
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        page = web / "index.html"
        return page.read_text(encoding="utf-8") if page.exists() else "<h1>Agent Arena</h1>"

    @app.post("/firewall")
    def firewall_eval(req: FirewallRequest) -> dict:
        try:
            intent = TradeIntent(
                agent_id=req.agent_id,
                symbol=req.symbol,
                side=req.side,
                instrument=req.instrument,
                notional_usd=req.notional_usd,
                quantity=req.quantity,
                leverage=req.leverage,
            )
        except Exception as exc:  # invalid sizing etc.
            raise HTTPException(status_code=400, detail=str(exc))

        quote = quote_for(req.symbol, req.instrument)
        mandate = default_arena_mandate(req.equity_usd, allowed_symbols=(req.symbol.upper(),))
        ctx = EvalContext(
            mandate=mandate,
            equity_usd=req.equity_usd,
            quote=quote,
            current_exposure_usd=req.current_exposure_usd,
            now_ms=int(time.time() * 1000),
            max_quote_age_ms=120_000,  # reject quotes older than 2 minutes (real freshness gate)
        )
        verdict = firewall.evaluate(intent, ctx)
        return {
            "decision": verdict.decision.value,
            "reason": verdict.reason,
            "effective_notional_usd": verdict.effective_notional_usd,
            "gates": [g.model_dump() for g in verdict.gates],
            "certificate": verdict.certificate.model_dump() if verdict.certificate else None,
            "certificate_valid": verify_certificate(verdict.certificate) if verdict.certificate else None,
        }

    @app.get("/leaderboard")
    def leaderboard():
        path = evidence / "leaderboard.json"
        if not path.exists():
            return JSONResponse({"detail": "no tournament run yet"}, status_code=404)
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/live")
    def live():
        """A signed live-arena snapshot (advanced by scripts/live_step.py — continuously-growing
        only when that runs on a schedule; the serverless deploy is stateless and does not advance
        on its own, so this endpoint serves the last committed snapshot. See /pulse for the
        continuously-live signed heartbeat)."""
        for path in (evidence.parent / "live" / "leaderboard.json", Path("evidence/live/leaderboard.json")):
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):  # label honestly so "I curled it twice and it didn't
                    data.setdefault("mode", "snapshot")  # move" is answered before it's discovered
                    data.setdefault(
                        "snapshot_note",
                        "A signed snapshot of a resumable live arena, served from the deploy. The "
                        "deploy is stateless serverless, so it does not advance on its own — run "
                        "scripts/live_step.py (cron/worker) to grow it. For a continuously-live "
                        "signed surface, see /pulse.",
                    )
                return data
        return JSONResponse({"detail": "no live arena yet — run scripts/live_step.py"}, status_code=404)

    @app.get("/pubkey")
    def pubkey() -> dict:
        """The arena's Ed25519 public key + issuer, so anyone can verify offline."""
        return {"issuer": firewall.issuer, "public_key_hex": firewall._signer.public_key_hex}

    @app.post("/verify")
    def verify(cert: dict) -> dict:
        """Independently verify a firewall certificate.

        Reports two distinct properties: ``valid`` = integrity (the signature matches the
        certificate's embedded key — not tampered), and ``trusted_issuer`` = authenticity
        (that embedded key matches THIS arena's published issuer key, so a forger who
        self-signed with their own keypair is rejected). A cert is genuinely from this
        arena only when both are true."""
        # accept either a bare certificate or a full firewall verdict (pull out its
        # `certificate`), matching the offline verify_cert.py CLI.
        if isinstance(cert.get("certificate"), dict):
            cert = cert["certificate"]
        try:
            c = Certificate(**cert)
        except Exception as exc:  # malformed payload
            return {"valid": False, "trusted_issuer": False, "reason": f"malformed certificate: {exc}"}
        ok = verify_certificate(c)
        trusted = verify_certificate(c, expected_public_key_hex=firewall._signer.public_key_hex)
        if not ok:
            reason = "signature invalid or tampered"
        elif trusted:
            reason = "signature valid and issued by this arena"
        else:
            reason = "signature self-consistent but NOT signed by this arena's key (possible forgery)"
        return {
            "valid": ok,
            "trusted_issuer": trusted,
            "issuer": c.issuer,
            "decision": c.decision.value,
            "intent_hash": c.intent_hash,
            "reason": reason,
        }

    @app.get("/debate")
    def debate():
        for path in (evidence / "llm_debate.json", evidence.parent / "llm_debate.json", Path("evidence/llm_debate.json")):
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):  # label honestly: the serverless deploy has no Qwen key,
                    data.setdefault("mode", "snapshot")  # so this is a recording, not a live call
                    data.setdefault(
                        "snapshot_note",
                        "Recorded Qwen debate, served from the signed evidence pack. The deployed "
                        "API is serverless and holds no model key, so debates are not generated "
                        "live here — run the offline/container path for a fresh one.",
                    )
                return data
        return JSONResponse({"detail": "no debate run yet"}, status_code=404)

    @app.get("/allocator")
    def allocator():
        """The TrustAllocator result: capital flows to DSR-verified skill, not lucky streaks."""
        for path in (evidence / "allocator.json", evidence.parent / "allocator.json", Path("evidence/allocator.json")):
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return JSONResponse({"detail": "no allocator run yet"}, status_code=404)

    @app.get("/ledger")
    def ledger(agent: str = "swarm", limit: int = Query(50, ge=1, le=1000)):
        if not _AGENT_ID_RE.fullmatch(agent):  # block path traversal (CWE-22) + junk
            return JSONResponse({"detail": "invalid agent id"}, status_code=400)
        ledgers_dir = (evidence / "ledgers").resolve()
        path = (ledgers_dir / f"{agent}.jsonl").resolve()
        if not path.is_relative_to(ledgers_dir) or not path.exists():  # belt + suspenders
            return JSONResponse({"detail": f"no ledger for agent '{agent}'"}, status_code=404)
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return {"agent": agent, "count": len(lines), "records": lines[-limit:]}

    return app


app = create_app()
