# Mean Reversion (RSI + Bands)

A contrarian strategy (策略) on ETH perpetual futures: it fades stretched moves —
buying oversold washouts and selling overbought pushes — and exits as price reverts
back toward its mean. It is the opposite style from a trend follower.

## Market behavior it captures

In range-bound or oscillating markets, price tends to snap back toward its recent
average after it gets stretched too far. This strategy harvests those reversions and
deliberately stays out when nothing is stretched.

## When it opens (开仓)

- **Long** when price is at an oversold extreme and near the lower volatility band.
- **Short** when price is overbought and pressed against the upper band.
- It waits for a genuine stretch rather than fading every wiggle.

## When it closes (平仓)

- A long is closed as price reverts toward the middle of its band and momentum
  normalizes; a short is closed symmetrically.
- It takes profit into the reversion — many small, quick round-trips, not big trends.

## Tunable parameters

- **Leverage** — scales gains and drawdowns equally; not a selectivity control.
- **Margin budget** — capital the platform sizes against and the return-% denominator.
- **Trading symbol** — applies the same reversion logic to another supported market.

## How to read the metrics

Mean-reversion systems usually show a higher win rate with smaller average wins. Read
return alongside max drawdown — a single strong trend can erase many small wins.

## Risks (风险)

The critical risk is a strong, sustained trend: fading a market that keeps running
produces a string of losing contrarian trades and the worst drawdowns this style can
incur. Breakouts, gap-driven news, thin liquidity, and persistent funding dislocation
also hurt it. Past historical backtest performance does not guarantee live results,
and live execution pays fees and slippage. Only use it with capital whose drawdown you
can tolerate.
