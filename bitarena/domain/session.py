"""US equity market-session classification for tokenized stocks.

Tokenized US stocks (rTokens like ``RAAPLUSDT``) trade 24/7 on Bitget, but their *underlying*
market is open only ~32.5h/week. Off-hours, the rToken price is "last-traded" — it can drift from
the (closed) underlying and gap at re-open. Classifying a timestamp as regular-session ``open`` vs
``closed`` lets the firewall treat off-hours tokenized-stock trading as higher-risk, and lets the
risk study quantify that risk.

DST-aware using the **post-2007** US rules (2nd Sunday of March → 1st Sunday of November; pre-2007
rules differed and are out of scope — the tokenized-stock data is current). It does **not** exclude
US market holidays — a holiday weekday is classified ``open`` by hour, a small, documented
over-count of open hours (the off-hours risk it measures is, if anything, *understated* as a result).
Self-contained: no ``tzdata`` dependency (zoneinfo has no tz database on Windows).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_OPEN_MIN = 9 * 60 + 30  # 09:30 ET
_CLOSE_MIN = 16 * 60     # 16:00 ET


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> int:
    """Day-of-month of the ``n``-th ``weekday`` (Mon=0…Sun=6) in ``year``/``month``."""
    first = datetime(year, month, 1).weekday()
    offset = (weekday - first) % 7
    return 1 + offset + (n - 1) * 7


def _us_dst(dt_utc: datetime) -> bool:
    """Whether US Eastern observes DST at this UTC instant (EDT) vs standard time (EST)."""
    y = dt_utc.year
    start = datetime(y, 3, _nth_weekday(y, 3, 6, 2), 7)   # 02:00 EST == 07:00 UTC, 2nd Sun Mar
    end = datetime(y, 11, _nth_weekday(y, 11, 6, 1), 6)   # 02:00 EDT == 06:00 UTC, 1st Sun Nov
    naive = dt_utc.replace(tzinfo=None)
    return start <= naive < end


def us_eastern(ts_ms: int) -> datetime:
    """Convert an epoch-ms timestamp to a naive US-Eastern ``datetime`` (DST-aware).

    Builds UTC via ``timedelta`` rather than ``datetime.fromtimestamp`` — the latter raises
    ``OSError`` on negative / pre-epoch timestamps on Windows, which would throw *out* of the
    fail-closed firewall. This keeps a malformed timestamp from ever crashing the gate.
    """
    dt_utc = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ts_ms)
    offset = -4 if _us_dst(dt_utc) else -5
    return (dt_utc + timedelta(hours=offset)).replace(tzinfo=None)


def us_equity_session(ts_ms: int) -> str:
    """``"open"`` during US regular equity hours (Mon–Fri 09:30–16:00 ET), else ``"closed"``."""
    et = us_eastern(ts_ms)
    if et.weekday() >= 5:  # Saturday / Sunday
        return "closed"
    minutes = et.hour * 60 + et.minute
    return "open" if _OPEN_MIN <= minutes < _CLOSE_MIN else "closed"


def is_market_open(ts_ms: int) -> bool:
    """Convenience boolean: is the underlying US market in regular session at ``ts_ms``?"""
    return us_equity_session(ts_ms) == "open"
