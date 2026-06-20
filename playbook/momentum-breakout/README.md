# Momentum Breakout (Donchian)

A classic breakout strategy (策略) on BTC perpetual futures: it enters when price
breaks beyond its recent trading channel and rides the move, exiting on a tighter
opposite channel that acts as a trailing stop.

## Market behavior it captures

Real directional moves usually begin when price pushes past the range it has held
recently. This strategy bets that such breaks tend to continue rather than reverse
immediately, and it deliberately avoids quiet, range-bound conditions where
breakouts are mostly false.

## When it opens (开仓)

- **Long** when price closes above the upper edge of its recent channel (bullish
  breakout).
- **Short** when price closes below the lower edge of its recent channel (bearish
  breakout).
- It waits for the range to actually give way rather than predicting the break.

## When it closes (平仓)

- A long is closed when price falls back through the lower edge of a shorter,
  tighter channel (trailing stop).
- A short is closed when price pushes back above the upper edge of that shorter
  channel.
- There is no fixed take-profit; winners run until the trailing channel breaks.

## Tunable parameters

- **Leverage** — amplifies gains and drawdowns equally; it does not make the
  strategy more selective.
- **Margin budget** — the capital the platform sizes orders against and the
  denominator for return percentage. Treat it as your maximum risk here.
- **Trading symbol** — applies the same breakout logic to another supported market.

## How to read the metrics

Look at strategy-basis return (net PnL over your margin budget) together with max
drawdown and trade count. Breakout systems typically show a lower win rate with
larger average wins than losses — judge them on the full curve, not win rate alone.

## Risks (风险)

The strategy underperforms in choppy, range-bound markets that generate repeated
false breakouts and whipsaw losses, and around gap-driven news that blows through
stops. Thin liquidity and persistent funding dislocation can also hurt results.
Past historical backtest performance does not guarantee live results, and live
execution pays fees and slippage. Only use it with capital whose drawdown you can
tolerate.
