"""LiveArena — a stateful, resumable tournament for continuous live operation.

The batch :class:`Arena` replays a whole series in one shot. ``LiveArena`` instead
processes *new* candles incrementally and persists everything between runs — each
agent's cash/position, the per-agent signed ledgers, the funding pointer, and the
last-processed timestamp — so it can be invoked on a schedule (cron / a deployed
worker) to drive a genuinely live, continuously-growing arena rather than a one-off
backtest. Re-feeding candles already seen is a no-op (idempotent by timestamp).

State lives under ``state_dir``: ``state.json`` (portfolios + cursor) and
``ledgers/<agent>.jsonl`` (the durable signed trade logs the batch arena also writes).
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

from ..agents.base import AgentObservation, TradingAgent
from ..connectors.paper import PaperExchange, ReplayMarketData
from ..domain.mandate import Mandate, default_arena_mandate
from ..domain.market import InstrumentType
from ..domain.verdict import Decision
from ..firewall.firewall import EvalContext, Firewall
from ..firewall.regime import assess_regime
from ..ledger.ledger import SignedLedger
from .engine import _SIM_MAX_QUOTE_AGE_MS, _cert_hash, _funding_price
from .leaderboard import build_leaderboard, cross_agent_pbo
from .portfolio import Portfolio


class LiveArena:
    """Resumable arena that advances on new candles and persists its state."""

    def __init__(
        self,
        *,
        agents: list[TradingAgent],
        symbol: str,
        instrument: InstrumentType,
        firewall: Firewall,
        state_dir: Path | str,
        starting_cash: float = 10_000.0,
        mandate: Mandate | None = None,
        funding: list[dict] | None = None,
    ) -> None:
        if not agents:
            raise ValueError("live arena needs at least one agent")
        self.symbol = symbol.upper()
        self.instrument = instrument
        self.firewall = firewall
        self.starting_cash = starting_cash
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.agents: dict[str, TradingAgent] = {a.agent_id: a for a in agents}
        self.mandate = mandate or default_arena_mandate(starting_cash, allowed_symbols=(self.symbol,))
        self._funding_index = sorted(
            (int(r["ts"]), float(r["funding_rate"]))
            for r in (funding or [])
            if "ts" in r and "funding_rate" in r
        )

        self.ledgers: dict[str, SignedLedger] = {
            aid: SignedLedger(firewall._signer, self.state_dir / "ledgers" / f"{aid}.jsonl")
            for aid in self.agents
        }
        self.portfolios: dict[str, Portfolio] = {}
        self.daily_counts: dict[str, int] = {}
        self.last_ts: int | None = None
        self._day: int | None = None
        self._last_funding_ts: int | None = None  # timestamp-based: robust to refetched funding lists
        self.firewall_totals = {"intents": 0, "allow": 0, "allow_capped": 0, "reject": 0, "exec_fail": 0}
        self.ticks_total = 0
        self._load()
        for aid in self.agents:
            self.portfolios.setdefault(aid, Portfolio(aid, starting_cash))
            self.daily_counts.setdefault(aid, 0)

    # -- persistence -------------------------------------------------------

    def _state_path(self) -> Path:
        return self.state_dir / "state.json"

    def _load(self) -> None:
        path = self._state_path()
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.last_ts = data.get("last_ts")
        self._day = data.get("day")
        self._last_funding_ts = data.get("last_funding_ts")
        self.daily_counts = dict(data.get("daily_counts", {}))
        self.firewall_totals = dict(data.get("firewall_totals") or self.firewall_totals)
        self.ticks_total = data.get("ticks_total", 0)
        for aid, p in (data.get("portfolios") or {}).items():
            pf = Portfolio(aid, self.starting_cash)
            pf.cash_usd = p["cash_usd"]
            pf.position_qty = p["position_qty"]
            pf.fees_paid = p.get("fees_paid", 0.0)
            pf.funding_received = p.get("funding_received", 0.0)
            pf.trades = p.get("trades", 0)
            pf.equity_curve = list(p.get("equity_curve") or [self.starting_cash])
            self.portfolios[aid] = pf
        for aid, st in (data.get("agent_states") or {}).items():
            agent = self.agents.get(aid)
            if agent is not None and hasattr(agent, "load_state_dict"):
                agent.load_state_dict(st)

    def _save(self) -> None:
        data = {
            "symbol": self.symbol,
            "instrument": self.instrument.value,
            "last_ts": self.last_ts,
            "day": self._day,
            "last_funding_ts": self._last_funding_ts,
            "daily_counts": self.daily_counts,
            "firewall_totals": self.firewall_totals,
            "ticks_total": self.ticks_total,
            "portfolios": {
                aid: {
                    "cash_usd": pf.cash_usd,
                    "position_qty": pf.position_qty,
                    "fees_paid": pf.fees_paid,
                    "funding_received": pf.funding_received,
                    "trades": pf.trades,
                    "equity_curve": pf.equity_curve,
                }
                for aid, pf in self.portfolios.items()
            },
            "agent_states": {
                aid: a.state_dict() for aid, a in self.agents.items() if hasattr(a, "state_dict")
            },
        }
        self._state_path().write_text(json.dumps(data), encoding="utf-8")

    # -- incremental processing -------------------------------------------

    def process(self, candles: list) -> dict:
        """Process candles newer than ``last_ts`` and persist. Idempotent by timestamp."""
        candles = list(candles)
        md = ReplayMarketData({self.symbol: candles})
        exchange = PaperExchange(md)
        new_candles = 0
        # resume funding by timestamp (robust to a refetched/shifted funding list)
        ts_index = [t for t, _ in self._funding_index]
        fptr = bisect.bisect_right(ts_index, self._last_funding_ts) if self._last_funding_ts is not None else 0
        prev_ts: int | None = None  # bracketing candle for funding-price interpolation across a gap
        prev_price: float | None = None

        for i, candle in enumerate(candles):
            if self.last_ts is not None and candle.ts <= self.last_ts:
                continue
            md.set_cursor(i)
            quote = md.get_quote(self.symbol, self.instrument)
            if quote is None or quote.mid <= 0:
                continue
            price, ts = quote.mid, quote.ts

            while fptr < len(self._funding_index) and self._funding_index[fptr][0] <= ts:
                self._last_funding_ts, rate = self._funding_index[fptr]
                fprice = _funding_price(self._last_funding_ts, prev_ts, prev_price, price, ts)
                for pf in self.portfolios.values():
                    pf.apply_funding(rate, fprice)
                fptr += 1
            prev_ts, prev_price = ts, price

            day = ts // 86_400_000
            if day != self._day:
                self._day = day
                self.daily_counts = {aid: 0 for aid in self.agents}

            regime = assess_regime(
                [c.close for c in md.get_candles(self.symbol, self.instrument, limit=12)]
            )

            for aid, agent in self.agents.items():
                pf = self.portfolios[aid]
                obs = AgentObservation(
                    symbol=self.symbol, instrument=self.instrument, ts=ts,
                    equity_usd=pf.equity(price), position_qty=pf.position_qty, price=price, market=md,
                )
                intent = agent.decide(obs)
                if intent is None:
                    continue
                self.firewall_totals["intents"] += 1
                ctx = EvalContext(
                    mandate=self.mandate, equity_usd=pf.equity(price), quote=quote,
                    current_exposure_usd=pf.exposure_usd(price), position_qty=pf.position_qty,
                    regime=regime, daily_count=self.daily_counts[aid],
                    now_ms=ts, max_quote_age_ms=_SIM_MAX_QUOTE_AGE_MS,
                )
                verdict = self.firewall.evaluate(intent, ctx)
                if verdict.decision is Decision.REJECT:
                    self.firewall_totals["reject"] += 1
                    continue
                self.firewall_totals["allow_capped" if verdict.decision is Decision.ALLOW_CAPPED else "allow"] += 1
                order = exchange.place_order(
                    symbol=intent.symbol, side=intent.side,
                    notional_usd=verdict.effective_notional_usd or 0.0,
                    instrument=intent.instrument, reduce_only=intent.reduce_only,
                )
                if not order.accepted:
                    self.firewall_totals["exec_fail"] += 1
                    continue
                before = pf.equity(price)
                pf.apply_fill(order)
                self.daily_counts[aid] += 1
                self.ledgers[aid].append(
                    ts=ts, agent_id=aid, symbol=order.symbol, side=order.side,
                    price=order.avg_price, quantity=order.filled_qty, notional_usd=order.notional_usd,
                    fee_usd=order.fee_usd, balance_before_usd=before, balance_after_usd=pf.equity(price),
                    decision=verdict.decision, cert_hash=_cert_hash(verdict),
                )

            for pf in self.portfolios.values():
                pf.mark(price)
            self.last_ts = ts
            self.ticks_total += 1
            new_candles += 1

        self._save()
        return self.snapshot(new_candles)

    def snapshot(self, new_candles: int = 0) -> dict:
        return {
            "symbol": self.symbol,
            "instrument": self.instrument.value,
            "last_ts": self.last_ts,
            "new_candles": new_candles,
            "ticks": self.ticks_total,
            "starting_cash": self.starting_cash,
            "issuer": self.firewall.issuer,
            "leaderboard": build_leaderboard(self.portfolios),
            "firewall": {"totals": dict(self.firewall_totals)},
            "overfitting": cross_agent_pbo(self.portfolios),
            "ledger_verified": all(self.ledgers[aid].verify()[0] for aid in self.ledgers),
            "ledger_entries": {aid: len(self.ledgers[aid]) for aid in self.ledgers},
            "funding_received": {aid: round(pf.funding_received, 6) for aid, pf in self.portfolios.items()},
        }
