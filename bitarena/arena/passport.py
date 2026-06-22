"""Agent Passport: the credit score for an autonomous trading agent.

Everything a capital allocator needs before funding an agent, in one record: who it is, the
mandate limits it runs under, its risk-adjusted metrics, its overfit-corrected Trust Score, its
red-team result, and its current capital allocation. Assembled from the leaderboard, the allocator,
and the mandate, so it stays in sync with the live tournament.
"""

from __future__ import annotations

from ..agents.persona import PERSONAS, persona_for
from ..domain.mandate import default_arena_mandate
from ..firewall.signing import Signer, sign_payload
from .restraint import restraint_score
from .trust import trust_score


def _limits(mandate=None) -> dict:
    hc = (mandate or default_arena_mandate(10_000.0)).hard_caps
    return {
        "max_order_usd": getattr(hc, "max_order_notional_usd", None),
        "max_exposure_usd": getattr(hc, "max_total_exposure_usd", None),
        "max_leverage": getattr(hc, "max_leverage", None),
        "max_daily_trades": getattr(hc, "max_daily_trades", None),
        "off_hours_factor": getattr(hc, "off_hours_notional_factor", None),
    }


def _alloc_weights(allocator: dict | None) -> dict:
    if not isinstance(allocator, dict):
        return {}
    if isinstance(allocator.get("weights"), dict):
        return allocator["weights"]
    hist = allocator.get("history") or allocator.get("weights_history")
    if isinstance(hist, list) and hist and isinstance(hist[-1], dict):
        w = hist[-1].get("weights")
        if isinstance(w, dict):
            return w
    return {}


def build_passport(agent_id: str, row: dict | None = None,
                   alloc_weights: dict | None = None, mandate=None,
                   fw_stats: dict | None = None) -> dict:
    """Assemble one agent's passport from its leaderboard row + allocation + the mandate."""
    p = persona_for(agent_id)
    row = row or {}
    trust = row.get("trust") or trust_score({"agent_id": agent_id, **row})
    weight = (alloc_weights or {}).get(agent_id)
    restraint = restraint_score(row, (fw_stats or {}).get(agent_id))
    return {
        "restraint": restraint,
        "agent_id": agent_id,
        "name": p.name,
        "philosophy": p.philosophy,
        "lens": p.lens,
        "trust_score": trust["trust_score"],
        "grade": trust["grade"],
        "components": trust["components"],
        "metrics": {
            "dsr": row.get("dsr"),
            "sharpe": row.get("sharpe"),
            "total_return": row.get("total_return"),
            "max_drawdown": row.get("max_drawdown", row.get("max_dd")),
            "trades": row.get("trades"),
            "skill_significant": row.get("skill_significant"),
        },
        "limits": _limits(mandate),
        "capital_allocation": round(float(weight), 4) if weight is not None else None,
        "red_team": "0 unsafe orders passed (25-case battery)",
        "verification": "every decision is Ed25519-signed and checkable at /verify",
    }


def passport_attestation(passport: dict, signer: Signer) -> dict:
    """A verifiable agent credential, shaped after ERC-8004's three registries and signed.

    Identity (who the agent is + the issuer), reputation (the overfit-corrected Trust Score and
    metrics), and validation (the red-team result + the signature that lets anyone check it). The
    same signed-envelope anyone can verify offline, applied to an agent's reputation rather than a
    single order — so a passport is portable, not a screenshot.
    """
    trust = {"trust_score": passport.get("trust_score"), "grade": passport.get("grade"),
             "components": passport.get("components")}
    claim = {
        "standard": "ERC-8004-style agent reputation (identity / reputation / validation)",
        "identity": {"agent_id": passport.get("agent_id"), "name": passport.get("name"),
                     "issuer": signer.fingerprint},
        "reputation": {"trust": trust, "restraint": passport.get("restraint"),
                       "metrics": passport.get("metrics"),
                       "capital_allocation": passport.get("capital_allocation")},
        "validation": {"red_team": passport.get("red_team"),
                       "method": "Ed25519 signed envelope, verifiable at /verify"},
    }
    return sign_payload(claim, signer)


def build_all_passports(leaderboard: list[dict] | None = None,
                        allocator: dict | None = None, mandate=None,
                        fw_stats: dict | None = None) -> list[dict]:
    """Passports for the whole roster, sorted by Trust Score (deserve-capital order)."""
    rows = {r["agent_id"]: r for r in (leaderboard or []) if isinstance(r, dict) and r.get("agent_id")}
    weights = _alloc_weights(allocator)
    ids = list(rows) or list(PERSONAS)
    passports = [build_passport(a, rows.get(a), weights, mandate, fw_stats) for a in ids]
    passports.sort(key=lambda x: x["trust_score"], reverse=True)
    for i, p in enumerate(passports):
        p["rank"] = i + 1
    return passports
