"""Track 3 depth: quantify off-hours risk in Bitget tokenized US stocks.

Tokenized stocks trade 24/7 on Bitget, but the underlying market is open ~32.5h/week. This study
measures, per stock on real 1h candles, how off-hours ("closed") price behaviour differs from
regular-session ("open") behaviour, and how large the gap is when the market re-opens — the
"ghost price" risk a session-aware firewall gate is built to contain. Honest + reproducible:

    uv run python scripts/tokenized_session_study.py        # or: make session-study

Writes evidence/tokenized_session_risk.json. Limitation: US market holidays are not excluded
(a holiday weekday counts as "open" by hour), which if anything *understates* the off-hours share.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from bitarena.connectors.bitget import BitgetPublicData
from bitarena.domain.market import InstrumentType
from bitarena.domain.session import us_equity_session

STOCKS = {
    "RAAPLUSDT": "Apple", "RTSLAUSDT": "Tesla", "RNVDAUSDT": "NVIDIA",
    "RMSFTUSDT": "Microsoft", "RGOOGLUSDT": "Alphabet", "RMETAUSDT": "Meta",
}

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass


def _std(xs: list[float]) -> float:
    return float(np.std(np.asarray(xs, dtype=float), ddof=1)) if len(xs) > 1 else 0.0


def _p95_abs(xs: list[float]) -> float:
    return float(np.percentile(np.abs(np.asarray(xs, dtype=float)), 95)) if xs else 0.0


def study_symbol(sym: str, candles: list) -> dict:
    closes = [float(c.close) for c in candles]
    ts = [int(c.ts) for c in candles]
    sessions = [us_equity_session(t) for t in ts]
    open_rets: list[float] = []
    closed_rets: list[float] = []
    reopen_gaps: list[float] = []  # the return on the first open bar after a closed run
    for i in range(1, len(closes)):
        if closes[i - 1] <= 0 or closes[i] <= 0:
            continue
        r = float(np.log(closes[i] / closes[i - 1]))
        (open_rets if sessions[i] == "open" else closed_rets).append(r)
        if sessions[i] == "open" and sessions[i - 1] == "closed":
            reopen_gaps.append(r)
    n = len(closes)
    closed_frac = sessions.count("closed") / n if n else 0.0
    open_vol, closed_vol = _std(open_rets), _std(closed_rets)
    return {
        "symbol": sym, "name": STOCKS[sym], "bars": n,
        "off_hours_bar_share": round(closed_frac, 4),
        "open_session_vol": round(open_vol, 6),
        "closed_session_vol": round(closed_vol, 6),
        # how much louder/quieter off-hours bars are vs regular session (1.0 == identical risk)
        "off_to_open_vol_ratio": round(closed_vol / open_vol, 3) if open_vol > 0 else None,
        "reopen_gaps": len(reopen_gaps),
        "reopen_gap_mean_abs_pct": round(100 * float(np.mean(np.abs(reopen_gaps))), 4) if reopen_gaps else 0.0,
        "reopen_gap_p95_abs_pct": round(100 * _p95_abs(reopen_gaps), 4),
    }


def reopen_pairs(candles: list) -> list[tuple[float, float]]:
    """(off-hours drift, following open-session cumulative return) for each closed→open transition.

    Used to ask whether off-hours dislocation REVERTS once the market re-opens (a correctable
    ghost price) or PERSISTS (informative) — the overfit-aware edge-or-noise question.
    """
    closes = [float(c.close) for c in candles]
    sessions = [us_equity_session(int(c.ts)) for c in candles]
    rets: list[tuple[str, float]] = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0 and closes[i] > 0:
            rets.append((sessions[i], float(np.log(closes[i] / closes[i - 1]))))
    runs: list[tuple[str, float]] = []  # maximal same-session runs as (session, cumret)
    cur, acc = None, 0.0
    for sess, r in rets:
        if sess != cur:
            if cur is not None:
                runs.append((cur, acc))
            cur, acc = sess, r
        else:
            acc += r
    if cur is not None:
        runs.append((cur, acc))
    return [(runs[j][1], runs[j + 1][1]) for j in range(len(runs) - 1)
            if runs[j][0] == "closed" and runs[j + 1][0] == "open"]


def _reversion(pooled: list[tuple[float, float]]) -> dict | None:
    """Pooled correlation of off-hours drift vs next-open move + a permutation significance test."""
    if len(pooled) < 20:
        return None
    zd = np.array([p[0] for p in pooled])
    zo = np.array([p[1] for p in pooled])
    corr = float(np.corrcoef(zd, zo)[0, 1])
    rng = np.random.default_rng(11)  # fixed seed → reproducible permutation p on the same data
    null = np.array([abs(float(np.corrcoef(zd, rng.permutation(zo))[0, 1])) for _ in range(2000)])
    p = float((null >= abs(corr)).mean())
    if p < 0.05:
        interp = ("off-hours moves significantly REVERT at re-open (the ghost price corrects) — "
                  "supports capping off-hours risk") if corr < 0 else \
                 "off-hours moves significantly PERSIST (informative)"
    else:
        interp = ("no significant predictability — off-hours moves are risk/noise, not a reliable "
                  "signal; capping (not trading) them is the right response")
    return {"n_transitions": len(pooled), "pooled_corr": round(corr, 4), "permutation_p": round(p, 4),
            "interpretation": interp, "note": "~3-4 weeks of 1h data; small sample, reported honestly"}


def main() -> int:
    client = BitgetPublicData()
    per_stock: list[dict] = []
    pooled: list[tuple[float, float]] = []  # per-stock-standardized (drift, next-open) pairs
    for sym in STOCKS:
        candles = client.get_candles(sym, InstrumentType.SPOT, timeframe="1h", limit=720)
        if not candles or len(candles) < 50:
            per_stock.append({"symbol": sym, "name": STOCKS[sym], "error": "insufficient data"})
            continue
        s = study_symbol(sym, candles)
        per_stock.append(s)
        pairs = reopen_pairs(candles)
        if len(pairs) >= 5:
            d = np.array([p[0] for p in pairs])
            o = np.array([p[1] for p in pairs])
            if d.std() > 0 and o.std() > 0:  # standardize within stock so stocks pool comparably
                pooled.extend(zip((d - d.mean()) / d.std(), (o - o.mean()) / o.std()))
        print(f"  {s['name']:<10} {sym:<11} bars={s['bars']:<4} off-hours={s['off_hours_bar_share']*100:4.1f}% "
              f"open_vol={s['open_session_vol']:.4f} closed_vol={s['closed_session_vol']:.4f} "
              f"ratio={s['off_to_open_vol_ratio']} reopen_p95={s['reopen_gap_p95_abs_pct']:.2f}%")
    client.close()

    ok = [s for s in per_stock if "error" not in s]
    ratios = [s["off_to_open_vol_ratio"] for s in ok if s.get("off_to_open_vol_ratio")]
    result = {
        "description": "Track 3 depth: off-hours ('closed') vs regular-session ('open') risk in "
                       "Bitget tokenized US stocks on real 1h candles — the ghost-price dislocation a "
                       "session-aware firewall gate contains. US holidays not excluded (understates off-hours).",
        "stocks": len(ok),
        "median_off_hours_bar_share": round(float(np.median([s["off_hours_bar_share"] for s in ok])), 4) if ok else None,
        "median_off_to_open_vol_ratio": round(float(np.median(ratios)), 3) if ratios else None,
        "max_reopen_gap_p95_abs_pct": round(max((s["reopen_gap_p95_abs_pct"] for s in ok), default=0.0), 4),
        "off_hours_reversion": _reversion(pooled),
        "per_stock": per_stock,
    }
    out = Path("evidence/tokenized_session_risk.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\n{len(ok)} stocks · median off-hours share {result['median_off_hours_bar_share']} · "
          f"median off/open vol ratio {result['median_off_to_open_vol_ratio']}")
    rev = result["off_hours_reversion"]
    if rev:
        print(f"reversion: n={rev['n_transitions']} corr={rev['pooled_corr']} perm_p={rev['permutation_p']} — {rev['interpretation']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
