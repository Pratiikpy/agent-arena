"""A signed trade memo: a short, named-section explanation of one firewall decision.

For a single decision it states the thesis, what the analyst signals said, the risk check the
firewall ran, and why it returned this verdict; it embeds the verdict's certificate hash and
signs the whole memo with the arena key. The prose is model-written when a key is present and a
factual template otherwise; every number comes from the verdict and the signals, never the model.
"""

from __future__ import annotations

import json
import re

from ..firewall.signing import Signer, model_canonical, sha256_hex, sign_payload, verify_payload
from ..llm import QwenClient
from ..perception.base import SignalBundle
from .persona import persona_for

_MEMO_SYS = (
    "You are an analyst writing a terse trade memo, one short paragraph per section. Use only the "
    "numbers given, no bullet points, no invented figures. Respond ONLY as compact JSON with keys "
    '"thesis","signals","risk","verdict", each at most 40 words.'
)


def _extract_json(text: str) -> dict | None:
    try:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except (ValueError, AttributeError):
        return None


def _gates_summary(verdict) -> str:
    gates = getattr(verdict, "gates", ()) or ()
    failed = [g for g in gates if not getattr(g, "passed", True)]
    if not failed:
        return f"All {len(gates)} firewall gates passed."
    parts = [f"{getattr(g, 'name', 'gate')}: {getattr(g, 'detail', '')}".strip() for g in failed]
    return "Gates that bound the order: " + "; ".join(parts) + "."


def build_memo(*, intent, verdict, bundle: SignalBundle | None, signer: Signer,
               llm: QwenClient | None = None) -> dict:
    """Build a signed trade memo for one firewall decision.

    ``intent`` is a TradeIntent, ``verdict`` a firewall Verdict (with gates + certificate).
    """
    persona = persona_for(intent.agent_id)
    requested = round(float(intent.notional_usd or 0.0), 2)
    effective = verdict.effective_notional_usd
    decision = verdict.decision.value if hasattr(verdict.decision, "value") else str(verdict.decision)
    net = round(float(bundle.net_signal), 3) if bundle else None
    agr = round(float(bundle.agreement), 3) if bundle else None
    n_sig = len(bundle.signals) if bundle else 0

    # factual template (always correct); the model, if available, only rephrases over these numbers
    sections = {
        "thesis": f"{persona.name} ({persona.lens}) proposed to {intent.side.value} "
                  f"{intent.symbol} for ${requested:,.0f}.",
        "signals": (f"Net signal {net:+.2f} at {agr:.2f} agreement across {n_sig} analyst views."
                    if bundle else "No analyst bundle was attached to this decision."),
        "risk": _gates_summary(verdict),
        "verdict": f"The firewall returned {decision}: {verdict.reason}. "
                   f"Effective size ${(effective or 0):,.0f}.",
    }

    source = "template"
    if llm is not None and llm.available():
        ctx = (f"Agent: {persona.name} ({persona.lens}). Intent: {intent.side.value} {intent.symbol} "
               f"${requested}. Net signal {net}, agreement {agr}, {n_sig} signals. "
               f"Verdict: {decision} ({verdict.reason}); effective ${effective}. {sections['risk']}")
        data = _extract_json(llm.chat(_MEMO_SYS, ctx) or "")
        if data and all(k in data for k in ("thesis", "signals", "risk", "verdict")):
            sections = {k: str(data[k])[:300] for k in ("thesis", "signals", "risk", "verdict")}
            source = "qwen"

    cert = getattr(verdict, "certificate", None)
    payload = {
        "agent": {"agent_id": intent.agent_id, "name": persona.name, "lens": persona.lens},
        "symbol": intent.symbol,
        "side": intent.side.value,
        "requested_usd": requested,
        "decision": decision,
        "effective_usd": effective,
        "reason": verdict.reason,
        "sections": sections,
        "source": source,
        "certificate_hash": sha256_hex(model_canonical(cert)) if cert else None,
    }
    return sign_payload(payload, signer)


def verify_memo(envelope: dict, expected_public_key_hex: str | None = None) -> bool:
    """Verify a signed trade memo. Integrity by default; pins the issuer if given. Never raises."""
    return verify_payload(envelope, expected_public_key_hex)
