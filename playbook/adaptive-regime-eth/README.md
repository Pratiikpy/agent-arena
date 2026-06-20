# Adaptive Regime (Conflict-Gated, ETH)

An adaptive ETH perpetual strategy (策略) that changes behavior with the market
regime instead of forcing one style on every condition. It trend-follows when the
market is clearly trending, mean-reverts when the market is clearly ranging, and
deliberately stays flat when the two reads conflict or conviction is weak.

## Market behavior it captures

Different regimes reward opposite behaviors. Sustained directional moves reward
trend-following; quiet, contained ranges reward fading extremes; and the worst
losses come from the ambiguous middle where signals disagree. This strategy reads
the regime first, then chooses the matching tactic — and treats "no position" as a
real decision when the regime is unclear.

## When it opens (开仓)

- **Trending regime** — when trend strength is high, it opens in the trend
  direction: long with upward momentum, short with downward momentum.
- **Ranging regime** — when trend strength is low, it fades stretched moves:
  long after an oversold washout, short after an overbought push, confirmed by a
  momentum oscillator plus a volatility-band position read.
- **Conflict / weak** — when trend strength is in between and the trend and
  mean-reversion reads disagree, it opens nothing.

## When it closes (平仓)

- A trend position closes when the directional read fades or flips.
- A range position closes as price reverts back toward the band center.
- Any position is closed when the regime turns ambiguous (conflict-gating).

## Tunable parameters

- **Leverage** — amplifies both gains and drawdowns equally; it does not make the
  strategy more selective.
- **Margin budget** — the capital the platform sizes orders against and uses as
  the denominator for return percentage. Treat it as your maximum risk on this
  Playbook.
- **Trading symbol** — re-applies the same regime logic to another supported
  market (BTCUSDT / ETHUSDT / SOLUSDT).

## How to read the metrics

The backtest reports a strategy-basis return (net PnL divided by your margin
budget) alongside the account-basis return (using the backtest starting balance).
Look at max drawdown and trade count together with return — a high return on very
few trades is less robust than a steadier curve.

## Risks (风险)

The strategy underperforms during fast regime transitions (a trend collapsing
into a range, or a range breaking into a trend) before the regime read catches up,
which can produce late entries or whipsaw exits. Gap moves around major news,
thin liquidity, and persistent funding dislocation can also hurt it. Past
historical backtest performance does not guarantee live results, and live trading
pays fees and slippage that erode edge. Only use this Playbook with capital whose
drawdown you can tolerate.
