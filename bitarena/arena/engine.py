"""The Arena: run competing agents over a market, gating every order through the firewall.

Each tick, for every agent: build its observation → it proposes an intent → the
firewall rules on it (signed) → an ALLOW/ALLOW_CAPPED is executed on the exchange
→ the fill updates the portfolio and is written to that agent's signed ledger. Then
every portfolio is marked to the current price. The result bundles the leaderboard,
firewall statistics (including how many unsafe orders were blocked), the cross-agent
overfitting check, and ledger-integrity verification.
"""

from __future__ import annotations

from pathlib import Path

from ..agents.base import AgentObservation, TradingAgent
from ..connectors.base import ExchangeConnector
from ..connectors.paper import ReplayMarketData
from ..domain.mandate import Mandate, default_arena_mandate
from ..domain.market import InstrumentType
from ..domain.verdict import Decision, Verdict
from ..firewall.firewall import EvalContext, Firewall
from ..firewall.regime import assess_regime
from ..firewall.signing import Signer, model_canonical, sha256_hex
from ..ledger.ledger import SignedLedger
from .leaderboard import build_leaderboard, cross_agent_pbo
from .portfolio import Portfolio

# In replayed/synthetic time the quote timestamp IS "now", so disable staleness.
_SIM_MAX_QUOTE_AGE_MS = 10 ** 15


def _funding_price(
    ts_f: int, prev_ts: int | None, prev_price: float | None, price: float, ts: int
) -> float:
    """Price to value a funding settlement at ``ts_f``, linearly interpolated between the
    bracketing candles ``(prev_ts, prev_price)`` and ``(ts, price)``. On a candle gap that
    spans several funding intervals this values each interval at its own time instead of
    settling them all at the latest price (which would over/under-charge the carry)."""
    if prev_ts is None or prev_price is None or ts <= prev_ts:
        return price
    if ts_f <= prev_ts:
        return prev_price
    frac = max(0.0, min(1.0, (ts_f - prev_ts) / (ts - prev_ts)))
    return prev_price + (price - prev_price) * frac


def _cert_hash(verdict: Verdict) -> str:
    if verdict.certificate is None:
        return ""
    return sha256_hex(model_canonical(verdict.certificate))


class Arena:
    """Runs a multi-agent tournament on one symbol against a replayable market."""

    def __init__(
        self,
        *,
        agents: list[TradingAgent],
        exchange: ExchangeConnector,
        market: ReplayMarketData,
        symbol: str,
        firewall: Firewall | None = None,
        signer: Signer | None = None,
        instrument: InstrumentType = InstrumentType.PERP,
        starting_cash: float = 10_000.0,
        mandate: Mandate | None = None,
        ledger_dir: Path | str | None = None,
        funding: list[dict] | None = None,
    ) -> None:
        if not agents:
            raise ValueError("arena needs at least one agent")
        self.symbol = symbol.upper()
        self.instrument = instrument
        self.market = market
        self.exchange = exchange
        self.starting_cash = starting_cash

        self._signer = signer or Signer.generate()
        self.firewall = firewall or Firewall(self._signer)
        self.mandate = mandate or default_arena_mandate(starting_cash, allowed_symbols=(self.symbol,))

        self.agents: dict[str, TradingAgent] = {a.agent_id: a for a in agents}
        self.portfolios: dict[str, Portfolio] = {
            aid: Portfolio(aid, starting_cash) for aid in self.agents
        }
        self.daily_counts: dict[str, int] = {aid: 0 for aid in self.agents}

        ledger_dir = Path(ledger_dir) if ledger_dir else None
        if ledger_dir is not None:
            # A batch tournament starts with FRESH ledgers, so re-running is idempotent
            # (no doubled records). Live resume/append is handled separately by LiveArena.
            ledger_dir.mkdir(parents=True, exist_ok=True)
            for aid in self.agents:
                (ledger_dir / f"{aid}.jsonl").unlink(missing_ok=True)
        self.ledgers: dict[str, SignedLedger] = {
            aid: SignedLedger(self._signer, ledger_dir / f"{aid}.jsonl" if ledger_dir else None)
            for aid in self.agents
        }

        # firewall accounting
        self.stats = {
            aid: {
                "intents": 0,
                "allow": 0,
                "allow_capped": 0,
                "reject": 0,
                "exec_fail": 0,
                "reject_reasons": {},
            }
            for aid in self.agents
        }
        self.ticks = 0
        self._day: int | None = None  # simulated UTC day for trade-count rollover
        self._funding_index = self._build_funding_index(funding)
        self._funding_ptr = 0
        self._funding_settlements = 0
        self._prev_ts: int | None = None  # previous candle (ts, mid) for funding-price interpolation
        self._prev_price: float | None = None

    @staticmethod
    def _build_funding_index(funding: list[dict] | None) -> list[tuple[int, float]]:
        items: list[tuple[int, float]] = []
        for row in funding or []:
            try:
                items.append((int(row["ts"]), float(row["funding_rate"])))
            except (TypeError, ValueError, KeyError):
                continue
        items.sort()
        return items

    # -- main loop ---------------------------------------------------------

    def run(self, ticks: int | None = None) -> dict:
        """Step the market until ``ticks`` steps elapse or the series ends."""
        steps = 0
        while ticks is None or steps < ticks:
            self._step()
            steps += 1
            if not self.market.advance():
                break
        self.ticks = steps
        return self.result()

    def _step(self) -> None:
        quote = self.market.get_quote(self.symbol, self.instrument)
        if quote is None or quote.mid <= 0:
            return
        price = quote.mid
        ts = quote.ts

        # settle any due perpetual funding on the positions held into the settlement
        # (longs pay shorts when the rate is positive); funding flows into cash -> equity
        while self._funding_ptr < len(self._funding_index) and self._funding_index[self._funding_ptr][0] <= ts:
            ts_f, rate = self._funding_index[self._funding_ptr]
            fprice = _funding_price(ts_f, self._prev_ts, self._prev_price, price, ts)
            for pf in self.portfolios.values():
                pf.apply_funding(rate, fprice)
            self._funding_ptr += 1
            self._funding_settlements += 1
        self._prev_ts, self._prev_price = ts, price

        # roll the per-day trade counters over at each simulated UTC-day boundary
        day = ts // 86_400_000
        if day != self._day:
            self._day = day
            self.daily_counts = {aid: 0 for aid in self.agents}

        # market-wide regime: one signal per tick, shared by every agent's evaluation
        regime = assess_regime(
            [c.close for c in self.market.get_candles(self.symbol, self.instrument, limit=12)]
        )

        for agent_id, agent in self.agents.items():
            pf = self.portfolios[agent_id]
            equity = pf.equity(price)
            obs = AgentObservation(
                symbol=self.symbol,
                instrument=self.instrument,
                ts=ts,
                equity_usd=equity,
                position_qty=pf.position_qty,
                price=price,
                market=self.market,
            )
            intent = agent.decide(obs)
            if intent is None:
                continue

            self.stats[agent_id]["intents"] += 1
            ctx = EvalContext(
                mandate=self.mandate,
                equity_usd=equity,
                quote=quote,
                current_exposure_usd=pf.exposure_usd(price),
                position_qty=pf.position_qty,
                regime=regime,
                daily_count=self.daily_counts[agent_id],
                now_ms=ts,
                max_quote_age_ms=_SIM_MAX_QUOTE_AGE_MS,
            )
            verdict = self.firewall.evaluate(intent, ctx)

            if verdict.decision is Decision.REJECT:
                self.stats[agent_id]["reject"] += 1
                reason = verdict.first_failure.gate if verdict.first_failure else "unknown"
                reasons = self.stats[agent_id]["reject_reasons"]
                reasons[reason] = reasons.get(reason, 0) + 1
                continue
            self.stats[agent_id]["allow_capped" if verdict.decision is Decision.ALLOW_CAPPED else "allow"] += 1

            order = self.exchange.place_order(
                symbol=intent.symbol,
                side=intent.side,
                notional_usd=verdict.effective_notional_usd or 0.0,
                instrument=intent.instrument,
                reduce_only=intent.reduce_only,
            )
            if not order.accepted:
                self.stats[agent_id]["exec_fail"] += 1
                continue

            balance_before = pf.equity(price)
            pf.apply_fill(order)
            self.daily_counts[agent_id] += 1
            balance_after = pf.equity(price)
            self.ledgers[agent_id].append(
                ts=ts,
                agent_id=agent_id,
                symbol=order.symbol,
                side=order.side,
                price=order.avg_price,
                quantity=order.filled_qty,
                notional_usd=order.notional_usd,
                fee_usd=order.fee_usd,
                balance_before_usd=balance_before,
                balance_after_usd=balance_after,
                decision=verdict.decision,
                cert_hash=_cert_hash(verdict),
            )

        for pf in self.portfolios.values():
            pf.mark(price)

    # -- reporting ---------------------------------------------------------

    def result(self) -> dict:
        leaderboard = build_leaderboard(self.portfolios)
        firewall_totals = {
            "intents": sum(s["intents"] for s in self.stats.values()),
            "allow": sum(s["allow"] for s in self.stats.values()),
            "allow_capped": sum(s["allow_capped"] for s in self.stats.values()),
            "reject": sum(s["reject"] for s in self.stats.values()),
            "exec_fail": sum(s["exec_fail"] for s in self.stats.values()),
        }
        ledger_ok = all(self.ledgers[aid].verify()[0] for aid in self.ledgers)
        return {
            "symbol": self.symbol,
            "instrument": self.instrument.value,
            "ticks": self.ticks,
            "starting_cash": self.starting_cash,
            "issuer": self.firewall.issuer,
            "leaderboard": leaderboard,
            "firewall": {"totals": firewall_totals, "by_agent": self.stats},
            "overfitting": cross_agent_pbo(self.portfolios),
            "ledger_verified": ledger_ok,
            "ledger_entries": {aid: len(self.ledgers[aid]) for aid in self.ledgers},
            "funding_settlements": self._funding_settlements,
            "funding_received": {
                aid: round(self.portfolios[aid].funding_received, 6) for aid in self.portfolios
            },
        }
