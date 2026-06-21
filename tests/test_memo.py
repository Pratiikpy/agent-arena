"""The signed trade memo: a named-section explanation of one firewall decision, tamper-evident."""

from __future__ import annotations

from bitarena.agents.memo import build_memo, verify_memo
from bitarena.domain import InstrumentType, Quote, Side, TradeIntent, default_arena_mandate
from bitarena.firewall import EvalContext, Firewall, Signer


def _verdict_for(notional: float):
    fw = Firewall(Signer.generate())
    intent = TradeIntent(agent_id="swarm", symbol="BTCUSDT", side=Side.BUY,
                         instrument=InstrumentType.PERP, notional_usd=notional)
    q = Quote(symbol="BTCUSDT", bid=99.95, ask=100.05, last=100.0, ts=1000)
    ctx = EvalContext(mandate=default_arena_mandate(10_000, allowed_symbols=("BTCUSDT",)),
                      equity_usd=10_000.0, quote=q, now_ms=1000, max_quote_age_ms=10 ** 15)
    return fw, intent, fw.evaluate(intent, ctx)


def test_memo_is_signed_factual_and_links_the_certificate():
    fw, intent, verdict = _verdict_for(50_000)  # oversized -> capped by the firewall
    memo = build_memo(intent=intent, verdict=verdict, bundle=None, signer=fw._signer, llm=None)
    assert verify_memo(memo) is True
    assert verify_memo(memo, expected_public_key_hex=fw._signer.public_key_hex) is True
    assert set(memo["sections"]) == {"thesis", "signals", "risk", "verdict"}
    assert memo["agent"]["name"] == "The Consensus"  # persona, not a raw id
    assert memo["decision"] in ("ALLOW", "ALLOW_CAPPED", "REJECT")
    assert memo["certificate_hash"]  # the memo is bound to the signed verdict
    assert memo["source"] == "template"  # no model -> factual template, never invented prose


def test_memo_tamper_is_caught():
    fw, intent, verdict = _verdict_for(50_000)
    memo = build_memo(intent=intent, verdict=verdict, bundle=None, signer=fw._signer, llm=None)
    memo["effective_usd"] = 999_999  # forge the size
    assert verify_memo(memo) is False
