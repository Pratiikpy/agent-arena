"""TrustAllocator — a meta-agent that allocates risk budget across competing agents.

The apex of the Arena thesis: don't just *rank* agents, *fund* them — and fund by *verified*
trust, not lucky streaks. Each agent's capital/risk budget is set by its rolling performance
(return penalized by drawdown), then **deflated by overfit-aware skill confidence** (a Deflated
Sharpe discount against the fleet): a positive run that can't be distinguished from the luckiest
draw is discounted, so capital flows to skill. Trusted agents get a larger mandate; likely-luck and
decaying agents are starved toward zero. This is the verification half (DSR/PBO) applied to capital,
not just to the leaderboard. The firewall still gates every order — so even a freshly-promoted agent
cannot breach its (now larger) mandate.

This reallocates a *risk budget* (the per-agent firewall mandate), not physical cash, so
there are no messy position transfers; the "fund" equity is the sum of the agents' slices.
Learned weights are persisted, so the allocator's trust compounds across runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..agents.base import AgentObservation, TradingAgent
from ..connectors.base import ExchangeConnector
from ..connectors.paper import ReplayMarketData
from ..domain.mandate import default_arena_mandate
from ..domain.market import InstrumentType
from ..domain.verdict import Decision
from ..firewall.firewall import EvalContext, Firewall
from ..scoring.metrics import max_drawdown, summarize, to_returns
from ..scoring.overfit import deflated_sharpe_ratio, sharpe_moments
from .portfolio import Portfolio


def rolling_score(equity_curve, lookback: int) -> float:
    """Rolling return over the lookback window, penalized by its drawdown."""
    e = np.asarray(equity_curve[-lookback:], dtype=float)
    if e.size < 3 or e[0] <= 0:
        return 0.0
    ret = e[-1] / e[0] - 1.0
    dd = abs(max_drawdown(e))
    return float(ret - 0.5 * dd)


def trust_weights(scores, *, temperature: float = 0.03, min_weight: float = 0.02, starve_below: float = -0.05) -> np.ndarray:
    """Softmax of scores into allocation weights; agents below ``starve_below`` are starved.

    Floors surviving agents at ``min_weight`` and renormalizes. If everyone is below the
    starve line, nobody is starved (the fund stays fully invested across all).
    """
    s = np.asarray(scores, dtype=float)
    alive = s > starve_below
    if not alive.any():
        alive = np.ones_like(s, dtype=bool)
    masked = np.where(alive, s, -np.inf)
    z = masked - np.max(masked[np.isfinite(masked)])
    w = np.where(np.isfinite(z), np.exp(z / max(temperature, 1e-6)), 0.0)
    if w.sum() <= 0:
        w = alive.astype(float)
    w = w / w.sum()
    w = np.where(alive, np.maximum(w, min_weight), 0.0)
    return w / w.sum()


class TrustAllocator:
    """Runs a fleet under a meta-allocator that funds agents by verified performance."""

    def __init__(
        self,
        *,
        agents: list[TradingAgent],
        exchange: ExchangeConnector,
        market: ReplayMarketData,
        symbol: str,
        firewall: Firewall | None = None,
        instrument: InstrumentType = InstrumentType.PERP,
        pool_usd: float = 50_000.0,
        rebalance_every: int = 50,
        lookback: int = 120,
        temperature: float = 0.03,
        min_weight: float = 0.02,
        starve_below: float = -0.05,
        max_leverage: float = 3.0,
        adaptive: bool = True,
        state_path: Path | str | None = None,
    ) -> None:
        if not agents:
            raise ValueError("allocator needs at least one agent")
        self.symbol = symbol.upper()
        self.instrument = instrument
        self.market = market
        self.exchange = exchange
        self.firewall = firewall or Firewall()
        self.pool_usd = pool_usd
        self.rebalance_every = rebalance_every
        self.lookback = lookback
        self.temperature = temperature
        self.min_weight = min_weight
        self.starve_below = starve_below
        self.max_leverage = max_leverage
        self.adaptive = adaptive
        self.state_path = Path(state_path) if state_path else None

        self.agents = {a.agent_id: a for a in agents}
        self.ids = list(self.agents)
        n = len(self.ids)
        self.portfolios = {aid: Portfolio(aid, pool_usd / n) for aid in self.ids}
        self.weights = {aid: 1.0 / n for aid in self.ids}
        if self.state_path and self.state_path.exists():
            self._load_state()  # compounding trust across runs
        self.weights_history: list[dict] = []
        self.fund_curve: list[float] = [pool_usd]
        self.allow = self.capped = self.reject = 0
        self.ticks = 0

    # -- loop --------------------------------------------------------------

    def run(self, ticks: int | None = None) -> dict:
        steps = 0
        while ticks is None or steps < ticks:
            if self.adaptive and steps > 0 and steps % self.rebalance_every == 0:
                self._rebalance(steps)
            self._step()
            steps += 1
            if not self.market.advance():
                break
        self.ticks = steps
        if self.state_path:
            self._save_state()
        return self.result()

    def _mandate_for(self, weight: float):
        capital = max(self.pool_usd * weight, 1.0)
        return default_arena_mandate(capital, allowed_symbols=(self.symbol,), max_leverage=self.max_leverage)

    def _fleet_dsr(self) -> list[float]:
        """Per-agent Deflated Sharpe over the rolling window, deflated against the *fleet* as the
        trial set: how confident we are each agent's recent Sharpe is skill, not the luckiest draw
        across the competitors. NaN (degenerate window) → 1.0 (no discount, fail-safe)."""
        rets = [to_returns(self.portfolios[aid].equity_curve[-self.lookback:]) for aid in self.ids]
        moments = [sharpe_moments(r) for r in rets]
        srs = [m["sr"] for m in moments]
        sr_var = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
        n = len(self.ids)
        out: list[float] = []
        for m in moments:
            d = deflated_sharpe_ratio(m["sr"], m["n"], n, sr_var, skew=m["skew"], kurt=m["kurt"])
            out.append(1.0 if d != d else d)  # NaN → no discount
        return out

    def _rebalance(self, tick: int) -> None:
        scores = [rolling_score(self.portfolios[aid].equity_curve, self.lookback) for aid in self.ids]
        # Overfit-adjusted trust (the verification half, applied to capital): deflate each agent's
        # recent Sharpe against the fleet (DSR) and discount a positive rolling score that isn't
        # distinguishable from luck — so the allocator funds skill-confidence, not lucky streaks.
        # Losers (score <= 0) are untouched; they are already starved by the score itself.
        dsrs = self._fleet_dsr()
        adjusted = [s * dsrs[i] if s > 0 else s for i, s in enumerate(scores)]
        w = trust_weights(adjusted, temperature=self.temperature, min_weight=self.min_weight, starve_below=self.starve_below)
        self.weights = {aid: float(w[i]) for i, aid in enumerate(self.ids)}
        self.weights_history.append({
            "tick": tick,
            "weights": {aid: round(self.weights[aid], 4) for aid in self.ids},
            "scores": {aid: round(scores[i], 4) for i, aid in enumerate(self.ids)},
            "dsr": {aid: round(dsrs[i], 4) for i, aid in enumerate(self.ids)},
        })

    def _step(self) -> None:
        quote = self.market.get_quote(self.symbol, self.instrument)
        if quote is None or quote.mid <= 0:
            return
        price = quote.mid
        for aid in self.ids:
            pf = self.portfolios[aid]
            obs = AgentObservation(
                symbol=self.symbol, instrument=self.instrument, ts=quote.ts,
                equity_usd=pf.equity(price), position_qty=pf.position_qty, price=price, market=self.market,
            )
            intent = self.agents[aid].decide(obs)
            if intent is None:
                continue
            ctx = EvalContext(
                mandate=self._mandate_for(self.weights[aid]),
                equity_usd=pf.equity(price), quote=quote,
                current_exposure_usd=pf.exposure_usd(price), position_qty=pf.position_qty,
                now_ms=quote.ts, max_quote_age_ms=10 ** 15,
            )
            verdict = self.firewall.evaluate(intent, ctx)
            if verdict.decision is Decision.REJECT:
                self.reject += 1
                continue
            self.capped += verdict.decision is Decision.ALLOW_CAPPED
            self.allow += verdict.decision is Decision.ALLOW
            order = self.exchange.place_order(
                symbol=intent.symbol, side=intent.side,
                notional_usd=verdict.effective_notional_usd or 0.0,
                instrument=intent.instrument, reduce_only=intent.reduce_only,
            )
            if order.accepted:
                pf.apply_fill(order)
        # mark every portfolio (grows each agent's equity history for rolling scoring)
        self.fund_curve.append(sum(pf.mark(price) for pf in self.portfolios.values()))

    # -- state persistence -------------------------------------------------

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"weights": self.weights}, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            saved = data.get("weights", {})
            for aid in self.ids:
                if aid in saved:
                    self.weights[aid] = float(saved[aid])
            total = sum(self.weights.values()) or 1.0
            self.weights = {aid: self.weights[aid] / total for aid in self.ids}
        except (ValueError, OSError):
            pass

    # -- reporting ---------------------------------------------------------

    def result(self) -> dict:
        return {
            "symbol": self.symbol,
            "instrument": self.instrument.value,
            "ticks": self.ticks,
            "pool_usd": self.pool_usd,
            "adaptive": self.adaptive,
            "fund_final_equity": round(self.fund_curve[-1], 2),
            "fund": summarize(self.fund_curve),
            "final_weights": {aid: round(self.weights[aid], 4) for aid in self.ids},
            "per_agent": {
                aid: {
                    "final_equity": round(self.portfolios[aid].equity_curve[-1], 2),
                    "trades": self.portfolios[aid].trades,
                }
                for aid in self.ids
            },
            "firewall": {"allow": self.allow, "allow_capped": self.capped, "reject": self.reject},
            "rebalances": len(self.weights_history),
            "weights_history": self.weights_history,
        }
