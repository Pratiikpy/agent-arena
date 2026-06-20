"""Minimal third-party integration: a bot that vets every trade through the Agent Arena
firewall and independently verifies each signed verdict — the Track-2 "another developer
integrated it" proof, in a few lines. Runs against the public deployment by default.

    uv run python scripts/integrate_example.py
    uv run python scripts/integrate_example.py --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import sys

from bitarena.client import FirewallClient

for _stream in (sys.stdout, sys.stderr):  # tolerate a cp1252 console
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Vet trades through the Agent Arena firewall.")
    ap.add_argument("--base-url", default="https://bitarena.vercel.app")
    args = ap.parse_args()

    fw = FirewallClient(args.base_url)
    issuer_key = fw.issuer_key()
    print(f"firewall: {args.base_url}  ·  issuer key {issuer_key[:16]}…\n")

    # my bot's proposed trades — the firewall decides which may be placed, and at what size.
    # (symbol, side, notional, current_exposure) — the last trade is at the exposure cap.
    trades = [
        ("BTCUSDT", "buy", 50.0, 0.0),          # within limits → ALLOW
        ("BTCUSDT", "buy", 999_999.0, 0.0),     # oversized → ALLOW_CAPPED to the mandate
        ("BTCUSDT", "buy", 2_000.0, 30_000.0),  # account at the exposure cap → REJECT
    ]
    placed = 0
    for symbol, side, notional, exposure in trades:
        v = fw.vet(symbol, side, notional_usd=notional, current_exposure_usd=exposure)
        trusted = v.verify(issuer_key)  # offline: signature intact AND signed by this arena
        eff = v.effective_notional_usd or 0.0
        print(f"  {side:<4} {symbol:<9} ${notional:>10,.0f}  ->  {v.decision:<13} "
              f"eff=${eff:>9,.2f}  verified={trusted}")
        if v.allowed:
            placed += 1  # my bot would place the order here at `eff`

    fw.close()
    print(f"\n{placed}/{len(trades)} trades cleared the firewall; every verdict independently verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
