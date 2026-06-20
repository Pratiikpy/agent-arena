"""Property/fuzz tests — the signed ledger's tamper-evidence must hold over random
ledgers and random tamper points, not just the three hand-picked cases in test_ledger.py.
"""

from __future__ import annotations

import random

from bitarena.domain.market import Side
from bitarena.domain.verdict import Decision
from bitarena.firewall.signing import Signer
from bitarena.ledger.ledger import SignedLedger


def _random_ledger(rng: random.Random, n: int) -> SignedLedger:
    led = SignedLedger(Signer.generate())
    bal = 10_000.0
    for i in range(n):
        before, bal = bal, bal + rng.uniform(-500.0, 500.0)
        led.append(
            ts=1_700_000_000_000 + i * 60_000,
            agent_id=rng.choice(["swarm", "regime", "rl-qlearn", "persona-team"]),
            symbol="BTCUSDT",
            side=rng.choice([Side.BUY, Side.SELL]),
            price=rng.uniform(50_000.0, 70_000.0),
            quantity=rng.uniform(0.001, 0.05),
            notional_usd=rng.uniform(50.0, 3_000.0),
            fee_usd=rng.uniform(0.0, 2.0),
            balance_before_usd=before,
            balance_after_usd=bal,
            decision=Decision.ALLOW,
            cert_hash=f"{rng.getrandbits(64):016x}",
        )
    return led


def test_clean_chains_always_verify_and_link():
    rng = random.Random(7)
    for _ in range(50):
        n = rng.randint(2, 12)
        led = _random_ledger(rng, n)
        ok, issues = led.verify()
        assert ok and issues == []
        assert led.verify(expected_count=n)[0] is True
        for i in range(1, n):
            assert led.records[i].prev_hash == led.records[i - 1].record_hash


def test_any_single_field_mutation_is_detected():
    rng = random.Random(11)
    fields = ["quantity", "price", "notional_usd", "balance_after_usd", "fee_usd", "ts", "agent_id"]
    for _ in range(80):
        n = rng.randint(2, 10)
        led = _random_ledger(rng, n)
        i = rng.randrange(n)
        field = rng.choice(fields)
        rec = led._records[i]
        cur = getattr(rec, field)
        new = cur + "_x" if field == "agent_id" else (cur + 1.0 if isinstance(cur, float) else cur + 1)
        led._records[i] = rec.model_copy(update={field: new})
        assert led.verify()[0] is False


def test_reorder_is_detected():
    rng = random.Random(13)
    for _ in range(50):
        n = rng.randint(3, 10)
        led = _random_ledger(rng, n)
        i, j = rng.sample(range(n), 2)
        led._records[i], led._records[j] = led._records[j], led._records[i]
        assert led.verify()[0] is False


def test_midchain_deletion_is_detected():
    rng = random.Random(17)
    for _ in range(50):
        n = rng.randint(3, 10)
        led = _random_ledger(rng, n)
        del led._records[rng.randrange(n - 1)]  # any non-tail record
        assert led.verify()[0] is False


def test_tail_truncation_needs_expected_count():
    # Dropping the newest record leaves a self-consistent prefix: plain verify() can't
    # see it, but verify(expected_count=...) — the arena knows the count — catches it.
    rng = random.Random(23)
    for _ in range(40):
        n = rng.randint(2, 10)
        led = _random_ledger(rng, n)
        del led._records[-1]
        assert led.verify()[0] is True  # honest: a bare hash chain misses truncation
        ok, issues = led.verify(expected_count=n)
        assert ok is False and any("truncation" in s for s in issues)
