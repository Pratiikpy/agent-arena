"""A transcribed, signed bull-vs-bear-vs-risk debate.

The LLM agent's conviction comes from a debate. This turns that debate into a first-class,
tamper-evident artifact: a multi-turn transcript (a bull case, a bear rebuttal, and a
risk-checked judgment) plus the final stance and conviction, signed with the arena key so
anyone can confirm the transcript was not edited after the fact. It runs on Qwen when a key is
present, with a deterministic fallback built from the net signal and analyst agreement, so it
always produces a transcript and a decision.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ..firewall.signing import Signer, sign_payload, verify_payload
from ..llm import QwenClient
from ..perception.base import SignalBundle

_BULL_SYS = "You are the Bull analyst on a crypto desk. Make the strongest evidence-based case to BUY, in 2-3 sentences."
_BEAR_SYS = "You are the Bear analyst. Rebut the bull and make the case to SELL or stay flat, in 2-3 sentences."
_JUDGE_SYS = (
    "You are the risk manager and judge. Weigh the bull and bear, lower conviction when the "
    "analysts disagree, and decide. Respond ONLY as compact JSON: "
    '{"stance":"long|short|flat","conviction":0..1,"reason":"<=20 words"}.'
)


def _extract_json(text: str) -> dict | None:
    try:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else None
    except (ValueError, AttributeError):
        return None


@dataclass
class Turn:
    role: str  # "bull" | "bear" | "judge"
    text: str


@dataclass
class DebateResult:
    symbol: str
    ts: int
    net_signal: float
    agreement: float
    transcript: list[Turn]
    stance: str  # long | short | flat
    conviction: float  # 0..1
    reason: str
    source: str  # "qwen" | "deterministic"
    signals: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "ts": int(self.ts),
            "net_signal": round(float(self.net_signal), 6),
            "agreement": round(float(self.agreement), 6),
            "transcript": [asdict(t) for t in self.transcript],
            "stance": self.stance,
            "conviction": round(float(self.conviction), 6),
            "reason": self.reason,
            "source": self.source,
            "signals": self.signals,
        }


class DebateSession:
    """Runs a bull/bear/judge debate over a signal bundle and returns a structured result."""

    def __init__(self, llm: QwenClient | None = None) -> None:
        self._llm = llm if llm is not None else QwenClient.from_settings()

    def run(self, bundle: SignalBundle) -> DebateResult:
        signals = [
            {"name": s.name, "source": s.source, "value": round(float(s.value), 4),
             "confidence": round(float(s.confidence), 4), "detail": s.detail}
            for s in bundle.signals
        ]
        net, agr = float(bundle.net_signal), float(bundle.agreement)
        brief = "\n".join(
            f"- {s['name']} ({s['source']}): value={s['value']:+.2f} conf={s['confidence']:.2f}"
            for s in signals
        )
        ctx = f"Symbol {bundle.symbol}. Analyst signals (value in [-1,1], + bullish):\n{brief}\nNet={net:+.2f}, agreement={agr:.2f}."

        source = "deterministic"
        if self._llm.available():
            bull = self._llm.chat(_BULL_SYS, ctx)
            bear = self._llm.chat(_BEAR_SYS, f"{ctx}\nBull said: {bull or '(n/a)'}")
            judge_raw = self._llm.chat(_JUDGE_SYS, f"{ctx}\nBull: {bull or '(n/a)'}\nBear: {bear or '(n/a)'}")
            data = _extract_json(judge_raw or "")
            if bull and bear and data:
                source = "qwen"
                stance = str(data.get("stance", "flat")).lower()
                try:
                    conviction = max(0.0, min(1.0, float(data.get("conviction", 0.0))))
                except (TypeError, ValueError):
                    conviction = 0.0
                if stance not in ("long", "short", "flat"):
                    stance = "flat"
                reason = str(data.get("reason", ""))[:140]
                transcript = [Turn("bull", bull.strip()), Turn("bear", bear.strip()),
                              Turn("judge", reason or f"stance {stance} at conviction {conviction:.2f}")]
                return DebateResult(bundle.symbol, bundle.ts, net, agr, transcript,
                                    stance, conviction, reason, source, signals)

        # deterministic fallback: a transcript and a decision derived from the real signals
        stance, conviction, reason, transcript = self._deterministic(bundle.symbol, net, agr, signals)
        return DebateResult(bundle.symbol, bundle.ts, net, agr, transcript,
                            stance, conviction, reason, source, signals)

    @staticmethod
    def _deterministic(symbol, net, agr, signals):
        score = net * agr
        if abs(score) < 0.1:
            stance, conviction = "flat", round(min(1.0, abs(score)), 3)
        else:
            stance = "long" if score > 0 else "short"
            conviction = round(min(1.0, abs(score)), 3)
        ups = [s["name"] for s in signals if s["value"] > 0.1]
        downs = [s["name"] for s in signals if s["value"] < -0.1]
        bull = (f"Net signal is {net:+.2f}; bullish reads from {', '.join(ups) or 'few signals'} "
                f"argue for a long.")
        bear = (f"Agreement is only {agr:.2f}; {', '.join(downs) or 'conflicting reads'} argue caution, "
                f"so size must stay small.")
        reason = f"net {net:+.2f} at {agr:.2f} agreement -> {stance} (conviction {conviction:.2f})"
        judge = f"Disagreement priced in. Decision: {stance}, conviction {conviction:.2f}."
        return stance, conviction, reason, [Turn("bull", bull), Turn("bear", bear), Turn("judge", judge)]


def sign_debate(result: DebateResult, signer: Signer) -> dict:
    """Wrap a debate result in a signed, tamper-evident envelope (arena Ed25519 key)."""
    return sign_payload(result.to_dict(), signer)


def verify_debate(envelope: dict, expected_public_key_hex: str | None = None) -> bool:
    """Verify a signed debate envelope. Integrity by default; pins the issuer if given. Never raises."""
    return verify_payload(envelope, expected_public_key_hex)
