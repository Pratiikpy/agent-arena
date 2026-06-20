"""Mandate — the immutable bounded-autonomy contract the firewall enforces.

A clean reimplementation of the bounded-autonomy idea from Vibe-Trading (HKUDS,
MIT; see NOTICE): an agent may act freely *within* hard quantitative caps and a
structural universe, and the gate fail-closes on anything outside them. In the
arena, every competitor is issued an identical mandate so the firewall governs
them all on equal terms.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .market import InstrumentType


class HardCaps(BaseModel):
    """Quantitative ceilings the agent physically cannot exceed."""

    model_config = ConfigDict(frozen=True)

    account_funding_usd: float
    max_order_notional_usd: float
    max_total_exposure_usd: float
    max_leverage: float
    allowed_instruments: tuple[InstrumentType, ...]
    max_trades_per_day: int


class UniverseConstraint(BaseModel):
    """Structural symbol universe the agent selects *within* (not a fixed whitelist)."""

    model_config = ConfigDict(frozen=True)

    # Empty allowed_symbols == any symbol permitted, subject to the other filters.
    allowed_symbols: tuple[str, ...] = ()
    exclude_symbols: tuple[str, ...] = ()
    min_price_usd: float | None = None

    def permits(self, symbol: str) -> bool:
        """Whether ``symbol`` (case-insensitive) is allowed by the universe."""
        s = symbol.strip().upper()
        if s in {x.strip().upper() for x in self.exclude_symbols}:
            return False
        if self.allowed_symbols:
            return s in {x.strip().upper() for x in self.allowed_symbols}
        return True


class Mandate(BaseModel):
    """Immutable bounded-autonomy mandate for one agent channel."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    label: str = "default"
    hard_caps: HardCaps
    universe: UniverseConstraint
    expires_at: str | None = None  # ISO-8601 UTC; None == no expiry (arena default)


def default_arena_mandate(
    funding_usd: float = 10_000.0,
    *,
    allowed_symbols: tuple[str, ...] = (),
    max_leverage: float = 3.0,
) -> Mandate:
    """A sensible default mandate for an arena competitor.

    Per-order notional is capped at 20% of funding, total exposure at 1x funding
    times leverage headroom, and the instrument set covers spot, perps, and
    tokenized equities. Tuned for safety-by-default, not aggression.
    """
    return Mandate(
        label="arena-default",
        hard_caps=HardCaps(
            account_funding_usd=funding_usd,
            max_order_notional_usd=round(funding_usd * 0.20, 2),
            max_total_exposure_usd=round(funding_usd * max_leverage, 2),
            max_leverage=max_leverage,
            allowed_instruments=(
                InstrumentType.SPOT,
                InstrumentType.PERP,
                InstrumentType.TOKENIZED_EQUITY,
            ),
            max_trades_per_day=200,
        ),
        universe=UniverseConstraint(allowed_symbols=allowed_symbols),
    )
