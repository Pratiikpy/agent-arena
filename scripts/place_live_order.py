"""Place ONE real, firewall-gated, dust-sized order on Bitget — the paper → live step.

SAFETY, by design:
  * Dry-run by default — it places **nothing** unless you pass ``--confirm``. The dry-run
    previews the firewall-gated order from public market data with **no keys at all**.
  * Only ``--confirm`` needs Bitget **trade-permission** keys (read-only keys can fetch data
    but cannot place orders). Use a dedicated sub-account.
  * It only ever submits an order the firewall **ALLOWs**, at the firewall's effective
    (possibly capped) size — even your own real order is gated and signed.

The signed verdict + the Bitget order receipt are written to ``evidence/live_order_receipt.json``
— the verifiable "live trading record" (timestamp, pair, direction, price, quantity, balance).

    uv run python scripts/place_live_order.py              # DRY RUN — shows the gated verdict, places nothing
    uv run python scripts/place_live_order.py --confirm    # places the gated dust order (needs a trade key)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bitarena.config import load_settings
from bitarena.connectors.bitget import BitgetConnector, BitgetPublicData
from bitarena.domain import InstrumentType, Side, TradeIntent, default_arena_mandate
from bitarena.firewall import EvalContext, Firewall, verify_certificate

for _s in (sys.stdout, sys.stderr):  # tolerate a cp1252 console
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Place ONE firewall-gated dust order on Bitget.")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--side", default="buy", choices=["buy", "sell"])
    ap.add_argument("--notional", type=float, default=5.0, help="USDT notional (kept tiny)")
    ap.add_argument("--equity", type=float, default=None, help="account equity for the mandate")
    ap.add_argument("--confirm", action="store_true", help="actually place it (else dry-run)")
    ap.add_argument("--out", default="evidence/live_order_receipt.json")
    args = ap.parse_args()

    s = load_settings()
    side = Side.BUY if args.side == "buy" else Side.SELL
    has_keys = bool(s.bitget_api_key and s.bitget_secret_key and s.bitget_passphrase)
    if args.confirm and not has_keys:
        print("✗ --confirm needs Bitget TRADE-permission keys in .env (BITGET_API_KEY / SECRET / PASSPHRASE).")
        print("  read-only keys can fetch market data but cannot place orders. (The dry-run works without keys.)")
        return 2

    # The dry-run preview needs only public market data + the firewall; only placing (--confirm)
    # uses the authenticated connector. So the gated order can be previewed without credentials.
    pub = BitgetPublicData()
    quote = pub.get_quote(args.symbol, InstrumentType.SPOT)
    pub.close()
    if quote is None or quote.mid <= 0:
        print(f"✗ no live quote for {args.symbol}")
        return 2

    equity = args.equity or max(args.notional * 200.0, 1_000.0)
    fw = Firewall.with_settings(s)
    intent = TradeIntent(
        agent_id="owner-live-order", symbol=args.symbol, side=side,
        instrument=InstrumentType.SPOT, notional_usd=args.notional,
    )
    ctx = EvalContext(
        mandate=default_arena_mandate(equity, allowed_symbols=(args.symbol.upper(),)),
        equity_usd=equity, quote=quote, now_ms=quote.ts, max_quote_age_ms=120_000,
    )
    verdict = fw.evaluate(intent, ctx)
    cert = verdict.certificate

    print(f"firewall: {verdict.decision.value}  effective=${verdict.effective_notional_usd or 0:,.2f}  ({verdict.reason})")
    print(f"  signed={bool(cert)}  cert_valid={verify_certificate(cert) if cert else None}  issuer={fw.issuer}  BTC≈{quote.mid}")

    receipt: dict = {
        "intent": intent.model_dump(mode="json"),
        "verdict": {
            "decision": verdict.decision.value,
            "effective_notional_usd": verdict.effective_notional_usd,
            "reason": verdict.reason,
        },
        "certificate": cert.model_dump() if cert else None,
        "certificate_valid": verify_certificate(cert) if cert else None,
        "quote": {"symbol": args.symbol, "mid": quote.mid, "ts": quote.ts},
        "placed": False,
    }

    if not verdict.allowed:
        print("→ firewall did NOT allow this order; nothing to place.")
    elif not args.confirm:
        print(f"→ DRY RUN — firewall ALLOWs ${verdict.effective_notional_usd:,.2f}. "
              "Re-run with --confirm to place it for real.")
    else:
        eff = verdict.effective_notional_usd
        print(f"→ placing a REAL ${eff:,.2f} {args.side} on {args.symbol} (gated by the firewall)…")
        conn = BitgetConnector(s.bitget_api_key, s.bitget_secret_key, s.bitget_passphrase)
        res = conn.place_order(symbol=args.symbol, side=side, notional_usd=eff, instrument=InstrumentType.SPOT)
        conn.close()
        receipt["placed"] = bool(res.accepted)
        receipt["order"] = {
            "accepted": res.accepted, "order_id": getattr(res, "order_id", ""),
            "filled_qty": getattr(res, "filled_qty", 0.0), "avg_price": getattr(res, "avg_price", 0.0),
            "fee_usd": getattr(res, "fee_usd", 0.0), "reason": getattr(res, "reason", ""),
        }
        print(f"  → accepted={res.accepted} order_id={getattr(res, 'order_id', '')} {getattr(res, 'reason', '')}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
