"""Property/fuzz tests for the Bitget response parsers — the live-data boundary.

If Bitget returns a malformed or partial body (rate-limit, maintenance, format drift),
the parsers must degrade gracefully — never crash, and never let non-finite numbers
(inf/nan) poison a Candle/Quote/funding row that the arena then trades on.
"""

from __future__ import annotations

import math
import random

from bitarena.connectors.bitget.client import BitgetPublicData
from bitarena.domain.market import Candle, Quote

ADVERSARIAL = [
    "inf", "-inf", "nan", "Infinity", "NaN", "1e400", "-1e400", "1e-400",
    "9" * 40, "  ", "1,000", "", "0x10", None, True, False,
]


def _rand_val(rng: random.Random, depth: int = 0):
    opts = [
        None, True, False,
        rng.randint(-10**9, 10**9), rng.uniform(-1e12, 1e12),
        rng.choice(ADVERSARIAL), "x" * rng.randint(0, 6),
    ]
    if depth < 3:
        opts.append([_rand_val(rng, depth + 1) for _ in range(rng.randint(0, 5))])
        keys = ["data", "symbol", "lastPr", "bidPr", "askPr", "ts", "fundingRate", "fundingTime", "junk"]
        opts.append({rng.choice(keys): _rand_val(rng, depth + 1) for _ in range(rng.randint(0, 5))})
    return rng.choice(opts)


def _rand_row(rng: random.Random):
    pool = ADVERSARIAL + [str(rng.uniform(1, 70_000)), rng.uniform(1, 70_000)]
    return [rng.choice(pool) for _ in range(rng.randint(0, 8))]


def test_parsers_never_crash_and_never_emit_nonfinite():
    rng = random.Random(42)
    for _ in range(4_000):
        if rng.random() < 0.5:
            payload = {"data": [_rand_row(rng) for _ in range(rng.randint(0, 5))]}
        else:
            payload = _rand_val(rng)

        candles = BitgetPublicData._parse_candles(payload)
        assert isinstance(candles, list)
        for c in candles:
            assert isinstance(c, Candle)
            for v in (c.ts, c.open, c.high, c.low, c.close, c.volume):
                assert math.isfinite(v)

        funding = BitgetPublicData._parse_funding(payload)
        assert isinstance(funding, list)
        for row in funding:
            assert math.isfinite(row["funding_rate"]) and math.isfinite(row["ts"])

        q = BitgetPublicData._parse_ticker(payload, "BTCUSDT")
        assert q is None or isinstance(q, Quote)
        if q is not None:
            for v in (q.bid, q.ask, q.last, q.ts):
                assert math.isfinite(v)
