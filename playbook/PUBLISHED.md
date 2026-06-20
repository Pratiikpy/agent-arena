# Published Bitget GetAgent Playbooks

Agent Arena is a **Playbook factory**: it authors, validates, backtests, and publishes
strategies straight to **Bitget's own GetAgent / Playbook platform** — on-platform,
reproducible backtests using the exact toolkit the hackathon provides. **Four are
published** (all `backtest_support: full`, real equity curves) — and three more were
backtested and deliberately *withheld* (see below):

| Playbook | strategy_id | Sharpe | Profit factor | Budget return |
|---|---|---|---|---|
| Adaptive Regime (Conflict-Gated, BTC) | `93af5b33-…-b653c68f6558` | 0.72 | 1.74 | +13.1% |
| Momentum Breakout (Donchian, BTC) | `7f86f156-…-731da4e3ec4f` | 1.68 | 2.33 | +39.7% |
| Momentum Breakout (Donchian, ETH) | `849d200f-…-708a472556d5` | 0.58 | 1.42 | +15.8% |
| Adaptive Regime (Conflict-Gated, ETH) | `1fb29226-…-9a18a03ee539` | 2.15 | 3.34 | +0.05% |

> **Basis note (so the numbers can't mislead):** "Budget return" is net PnL ÷ the **$1,000
> strategy budget** — i.e. ≈100× the account-basis return, because each strategy traded a $1k
> budget inside a ~$100k account. Drawdowns are reported **account-basis**. To compare return
> and drawdown on *one* basis, use the account-basis figures (e.g. BTC breakout: **+0.40%
> return vs 0.26% drawdown** — not the cross-basis +39.7% vs 0.26%).

The ETH regime row shows the honest tension the overfit-aware lens is built for: the
**best risk-adjusted ratios** of the set (Sharpe 2.15, profit factor 3.34) on a **near-flat
absolute return** (+$0.49 net) — the conflict-gate kept it highly selective on ETH, so it
rarely held a position. A high Sharpe on a tiny return is exactly the kind of result that
looks better than it is; it is published as a genuine positive, but the BTC books remain
the stronger absolute performers.

All visible on Bitget → Playbook → Explore. Details below.

## Identity (public)

- **Name:** `adaptive-regime-conflict-gated`
- **Display name:** Adaptive Regime (Conflict-Gated)
- **strategy_id:** `93af5b33-8a16-43ea-8e45-b653c68f6558`
- **version:** `0.0.1` · **status:** published
- **published_at:** 2026-06-20T08:40:53Z
- **backtest_support:** full · **official_evidence_kind:** backtest
- Visible on Bitget → Playbook → Explore: `https://www.bitget.com/zh-CN/activity/ai-get-agent/playbook?tab=explore`

## Official backtest (real run, 1,000 hourly BTC bars, real equity curve)

| Metric | Account basis | Strategy budget ($1,000) |
|---|---|---|
| Net PnL | +$131.22 | — |
| Total return | +0.13% | ≈ +13.1% |
| Sharpe | 0.72 | — |
| Sortino | 3.10 | — |
| Profit factor | 1.74 | — |
| Win rate | 44.1% (68 trades) | — |
| Max drawdown | 0.26% | — |
| Equity-curve points | 1,000 (real, not fabricated) | — |

Honest read: a **modest but genuinely positive** edge — wins larger than losses
(profit factor 1.74), low drawdown, real NAV curve. Past backtest performance does
not guarantee live results.

## Playbook 2 — Momentum Breakout (Donchian)

- **Name:** `momentum-breakout-btc` · **strategy_id:** `7f86f156-1034-4494-9969-731da4e3ec4f`
- **version:** `0.0.1` · **status:** published · **backtest_support:** full
- **Official backtest** (1,000 hourly BTC bars, real equity curve): net PnL **+$397** —
  **+0.40% account-basis** (≈+39.7% on the $1,000 deployed budget), **Sharpe 1.68**,
  **profit factor 2.33**, win rate 40.9% (44 trades), max drawdown **0.26% (account basis)** —
  return and drawdown on the same basis: +0.40% vs 0.26%. Classic breakout: fewer wins, larger winners.
- Package in [`momentum-breakout/`](./momentum-breakout/).

## Playbook 3 — Momentum Breakout (Donchian, ETH)

- **Name:** `momentum-breakout-eth` · **strategy_id:** `849d200f-5b58-459a-b610-708a472556d5`
- **version:** `0.0.1` · **status:** published · **backtest_support:** full
- **Official backtest** (1,000 hourly ETH bars, real equity curve): net PnL **+$158** —
  **+0.16% account-basis** (≈+15.8% on the $1,000 deployed budget), **Sharpe 0.58**,
  **profit factor 1.42**, win rate 28%
  (50 trades). The same validated breakout engine as the BTC Playbook, deployed to ETH —
  a genuine win on a second market (low win rate, larger winners; PF>1).
- Package in [`momentum-breakout-eth/`](./momentum-breakout-eth/).

## Researched but withheld — Mean Reversion (RSI + Bands), ETH

A third strategy ([`mean-reversion/`](./mean-reversion/)) was authored, validated, and
backtested on Bitget's platform — but **deliberately not published**, because the
evidence did not earn it. On the real ETH window (which trended), fading the move lost
money: net PnL −$165, total return −16.5% on budget, Sharpe −1.07, profit factor 0.95
(a 52% win rate undone by larger losses). Adding a stop-loss made it worse (whipsaw).
This is exactly the failure mode the strategy's own docs warn about — fading a sustained
trend.

Keeping it as a documented negative result rather than publishing a loser is the point:
the factory's discipline is **publish only when the evidence earns it.** The package is
in the repo, fully reproducible, as honest research.

## Researched but withheld — SOL (both strategies)

Both strategies were extended to a third asset, SOL, and **both underperformed** — a clean,
asset-specific result: SOL's higher volatility produced more false signals than either edge
could overcome.

- **Momentum Breakout, SOL** ([`momentum-breakout-sol/`](./momentum-breakout-sol/)):
  net −$0.14, **Sharpe −0.68**, profit factor 1.01 (breakeven), win 42.3% (52 trades).
- **Adaptive Regime, SOL** ([`adaptive-regime-sol/`](./adaptive-regime-sol/)):
  net −$0.16, **Sharpe −0.55**, profit factor 0.92 (loses), win 35.1% (74 trades).

The same engines that win on BTC and ETH break on SOL, so both SOL variants stay withheld.
This is the systematic, honest picture — two strategies × three assets, publish the four
winners, withhold the losers. Same discipline: publish only when the evidence earns it. Both
packages are in the repo, fully reproducible.

## Reproduce

The full package is in [`adaptive-regime/`](./adaptive-regime/) (manifest, README,
`src/strategy.py`, `src/main.py`, `backtest.yaml`). It is a deterministic
NautilusTrader strategy that fetches real Bitget/Binance hourly bars and replays
them in the GetAgent sandbox.

```bash
# validate locally (needs the getagent skill + PyYAML)
python3 <getagent-skill>/scripts/validate.py ./adaptive-regime/
# upload / run / publish use the GetAgent control-plane API with your Playbook key:
#   POST https://api.bitget.com/api/v1/playbook/{upload,run,publish}
```

The strategy mirrors Agent Arena's core idea: conviction comes from agreement
across reads, and "flat" is a deliberate decision when the regime is ambiguous.
