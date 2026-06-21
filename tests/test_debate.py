"""The signed debate artifact: a transcribed bull/bear/judge debate that verifies and is tamper-evident."""

from __future__ import annotations

from bitarena.agents.debate import DebateSession, sign_debate, verify_debate
from bitarena.firewall.signing import Signer
from bitarena.llm import QwenClient
from bitarena.perception.base import Signal, SignalBundle


def _offline_session() -> DebateSession:
    return DebateSession(llm=QwenClient(None, "x", "m"))  # no key -> deterministic fallback


def _bundle(values: list[float]) -> SignalBundle:
    sigs = [Signal(name=f"s{i}", source="test", value=v, confidence=0.8, detail="") for i, v in enumerate(values)]
    return SignalBundle(symbol="BTCUSDT", ts=1000, signals=sigs)


def test_deterministic_debate_produces_transcript_and_decision():
    res = _offline_session().run(_bundle([0.6, 0.5, 0.7]))  # strongly bullish, aligned
    assert res.source == "deterministic"
    assert [t.role for t in res.transcript] == ["bull", "bear", "judge"]
    assert all(t.text for t in res.transcript)  # no empty turns
    assert res.stance == "long" and 0.0 < res.conviction <= 1.0


def test_signed_debate_verifies_and_tamper_is_caught():
    signer = Signer.generate()
    env = sign_debate(_offline_session().run(_bundle([0.6, 0.5, 0.7])), signer)
    assert verify_debate(env) is True
    assert verify_debate(env, expected_public_key_hex=signer.public_key_hex) is True
    env["stance"] = "short"  # tamper a field
    assert verify_debate(env) is False


def test_conflicting_signals_yield_low_conviction():
    res = _offline_session().run(_bundle([0.6, -0.6, 0.5, -0.5]))  # cancel out -> low net x agreement
    assert res.stance in ("flat", "long", "short")
    assert res.conviction < 0.3
