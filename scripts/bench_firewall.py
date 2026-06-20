"""Latency benchmark for the firewall — how much overhead does gating every trade add?

Times the full ``Firewall.evaluate`` path (all risk gates + Ed25519 certificate
signing) over many iterations and reports p50/p95/p99 latency and throughput. The
answer matters: a trust layer is only viable if it is effectively free per trade.

    uv run python scripts/bench_firewall.py --iters 20000
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from bitarena.domain import Quote, Side, TradeIntent, default_arena_mandate
from bitarena.firewall import EvalContext, Firewall, Signer, verify_certificate


def main() -> None:
    parser = argparse.ArgumentParser(description="Firewall latency benchmark.")
    parser.add_argument("--iters", type=int, default=20_000)
    parser.add_argument("--out", default="evidence/firewall_bench.json")
    args = parser.parse_args()

    fw = Firewall(Signer.generate())
    quote = Quote(symbol="BTCUSDT", bid=99.95, ask=100.05, last=100.0, ts=1_000)
    ctx = EvalContext(
        mandate=default_arena_mandate(10_000),
        equity_usd=10_000.0,
        quote=quote,
        current_exposure_usd=0.0,
        daily_count=0,
        halted=False,
        now_ms=1_000,
        max_quote_age_ms=60_000,
    )
    intent = TradeIntent(agent_id="bench", symbol="BTCUSDT", side=Side.BUY, notional_usd=50.0)

    # warmup (JIT-free Python, but warms caches / imports)
    for _ in range(200):
        fw.evaluate(intent, ctx)

    # confirm the signed cert actually verifies (we are timing real work, not a stub)
    assert verify_certificate(fw.evaluate(intent, ctx).certificate) is True

    times_ms = []
    for _ in range(args.iters):
        t0 = time.perf_counter()
        fw.evaluate(intent, ctx)
        times_ms.append((time.perf_counter() - t0) * 1_000.0)

    times_ms.sort()

    def pct(p: float) -> float:
        idx = min(len(times_ms) - 1, max(0, int(p / 100.0 * len(times_ms)) - 1))
        return times_ms[idx]

    total_s = sum(times_ms) / 1_000.0
    report = {
        "iterations": args.iters,
        "includes_ed25519_signing": True,
        "mean_ms": round(sum(times_ms) / len(times_ms), 5),
        "p50_ms": round(pct(50), 5),
        "p95_ms": round(pct(95), 5),
        "p99_ms": round(pct(99), 5),
        "max_ms": round(times_ms[-1], 5),
        "throughput_per_sec": round(args.iters / total_s, 1) if total_s > 0 else None,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"firewall latency over {args.iters:,} signed verdicts:")
    print(f"  mean {report['mean_ms']:.4f} ms | p50 {report['p50_ms']:.4f} | p95 {report['p95_ms']:.4f} | p99 {report['p99_ms']:.4f} ms")
    print(f"  throughput ~{report['throughput_per_sec']:,.0f} verdicts/sec (single core, incl. Ed25519 signing)")
    print(f"evidence -> {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
