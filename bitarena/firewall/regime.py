"""Market-regime detection for the firewall's fleet-wide kill-switch.

The per-order gates bound what a *single* agent can do. This adds a *market-wide* layer:
when the market enters a fast crash, the firewall flips to ``FAST_RISK_OFF`` and the
kill-switch gate permits only de-risking (reduce-only) orders — every agent in the fleet
is forced to stop adding exposure at once, regardless of its own logic. The signal is a
pure function of recent prices, so it is deterministic and independently checkable.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum


class MarketRegime(str, Enum):
    """Coarse market state driving the firewall's kill-switch.

    NORMAL — business as usual. RISK_OFF — elevated stress (flagged, still tradable).
    FAST_RISK_OFF — an acute drawdown; the kill-switch engages (reduce-only).
    """

    NORMAL = "NORMAL"
    RISK_OFF = "RISK_OFF"
    FAST_RISK_OFF = "FAST_RISK_OFF"


def assess_regime(
    prices: Sequence[float],
    *,
    window: int = 12,
    fast_drawdown: float = 0.08,
    riskoff_drawdown: float = 0.04,
) -> MarketRegime:
    """Classify the regime from the recent peak-to-now drawdown over a short window.

    ``window`` is intentionally short (e.g. ~12 bars), so the drawdown captures a *fast*
    move rather than a slow grind. An acute drop (≥ ``fast_drawdown`` from the recent peak)
    is ``FAST_RISK_OFF``; a milder one (≥ ``riskoff_drawdown``) is ``RISK_OFF``; otherwise
    ``NORMAL``. Non-finite or too-short inputs fail safe to ``NORMAL`` (the kill-switch only
    *adds* restriction, so a missing signal must not silently engage it).
    """
    if not prices:
        return MarketRegime.NORMAL
    recent = [float(p) for p in list(prices)[-window:] if p is not None]
    recent = [p for p in recent if p == p and p not in (float("inf"), float("-inf"))]
    if len(recent) < 2:
        return MarketRegime.NORMAL
    # peak-to-now drawdown: the drop from the highest point in the window to the latest price
    peak = max(recent)
    if peak <= 0:
        return MarketRegime.NORMAL
    drawdown = (peak - recent[-1]) / peak
    if drawdown >= fast_drawdown:
        return MarketRegime.FAST_RISK_OFF
    if drawdown >= riskoff_drawdown:
        return MarketRegime.RISK_OFF
    return MarketRegime.NORMAL
