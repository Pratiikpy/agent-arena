"""Generate the five analyst briefs (the Agent Hub Skill outputs) from real Bitget market data, so
the agents react to real signals instead of the price-trend fallback. Each brief is
``{score, confidence, summary, source}`` written to ``evidence/briefs/{skill}_{SYMBOL}.json`` for
``AgentHubPerception`` to load.

Honesty about what is real: the ``technical`` read is real indicators (RSI + MA trend) computed
from real candles, and ``sentiment`` is the real Bitget funding rate (crowding/positioning). The
``macro``, ``news`` and ``onchain`` reads are honest proxies derived from the same real price,
volume and funding (a realized-volatility regime, return momentum, and a volume-flow tilt), each
labeled as such — they are not external Fed, news, or on-chain feeds.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def _clip(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def _rsi(closes: np.ndarray, n: int = 14) -> float:
    d = np.diff(closes)
    if d.size < n:
        return 50.0
    gains = np.clip(d[-n:], 0, None).mean()
    losses = np.clip(-d[-n:], 0, None).mean()
    if losses == 0:
        return 100.0
    return float(100.0 - 100.0 / (1.0 + gains / losses))


def compute_briefs(closes, volumes=None, funding_rate: float | None = None) -> dict[str, dict]:
    """Compute the five analyst briefs from real market series. ``funding_rate`` is the latest
    Bitget perpetual funding rate (per interval); ``volumes`` are per-bar volumes if available."""
    c = np.asarray([float(x) for x in closes], dtype=float)
    briefs: dict[str, dict] = {}

    # technical: real RSI + MA trend (real indicators on real candles)
    if c.size >= 21:
        sma5, sma20 = float(c[-5:].mean()), float(c[-20:].mean())
        trend = sma5 / sma20 - 1.0
        rsi = _rsi(c)
        score = _clip(trend * 25.0)
        conf = float(min(1.0, 0.5 + abs(trend) * 20.0))
        briefs["technical"] = {
            "score": round(score, 4), "confidence": round(conf, 3),
            "summary": f"RSI {rsi:.0f}, 5/20 MA trend {trend:+.2%}.", "source": "bitget-candles",
        }

    # sentiment: real funding rate (positive funding = crowded longs -> contrarian caution)
    if funding_rate is not None:
        fr = float(funding_rate)
        briefs["sentiment"] = {
            "score": round(_clip(-fr * 800.0), 4),
            "confidence": round(float(min(1.0, 0.4 + abs(fr) * 400.0)), 3),
            "summary": f"Funding {fr * 100:+.4f}% per interval; {'crowded longs' if fr > 0 else 'crowded shorts' if fr < 0 else 'balanced'}.",
            "source": "bitget-funding",
        }

    # macro proxy: longer trend tempered by realized volatility (risk-on/off from real price)
    if c.size >= 60:
        rets = np.diff(c[-60:]) / c[-60:-1]
        vol = float(np.std(rets)) if rets.size > 1 else 0.0
        long_trend = float(c[-1] / c[-60] - 1.0)
        score = _clip(long_trend * 6.0) * float(max(0.2, 1.0 - vol * 25.0))
        briefs["macro"] = {
            "score": round(score, 4), "confidence": round(float(max(0.2, 1.0 - vol * 20.0)), 3),
            "summary": f"60-bar trend {long_trend:+.2%}, realized vol {vol:.2%} (risk {'off' if vol > 0.03 else 'on'}).",
            "source": "bitget-derived (price regime, not external macro feeds)",
        }

    # news proxy: short-horizon return momentum (attention/momentum from real price)
    if c.size >= 11:
        roc = float(c[-1] / c[-11] - 1.0)
        briefs["news"] = {
            "score": round(_clip(roc * 15.0), 4), "confidence": 0.45,
            "summary": f"10-bar momentum {roc:+.2%} (attention proxy).",
            "source": "bitget-derived (momentum, not a news feed)",
        }

    # on-chain proxy: volume-flow tilt (recent volume surge x return sign) from real candle volume
    if volumes is not None and len(volumes) >= 20:
        v = np.asarray([float(x) for x in volumes], dtype=float)
        base = float(v[-20:].mean())
        surge = (float(v[-3:].mean()) / base - 1.0) if base > 0 else 0.0
        ret_sign = float(np.sign(c[-1] - c[-4])) if c.size >= 4 else 0.0
        briefs["onchain"] = {
            "score": round(_clip(surge * ret_sign), 4),
            "confidence": round(float(min(1.0, 0.4 + abs(surge))), 3),
            "summary": f"Volume {'surge' if surge > 0 else 'fade'} {surge:+.0%} into a {'up' if ret_sign > 0 else 'down'} move.",
            "source": "bitget-derived (volume flow, not an on-chain feed)",
        }
    return briefs


def write_briefs(briefs: dict[str, dict], symbol: str, out_dir: Path | str = "evidence/briefs") -> list[Path]:
    """Write each brief to ``{out_dir}/{skill}_{SYMBOL}.json`` (the path AgentHubPerception reads)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for skill, brief in briefs.items():
        p = out / f"{skill}_{symbol.upper()}.json"
        p.write_text(json.dumps({**brief, "symbol": symbol.upper(), "skill": skill}, indent=2), encoding="utf-8")
        written.append(p)
    return written
