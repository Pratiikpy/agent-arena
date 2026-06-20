# Agent Arena — Bitget AI Hackathon S1 Submission

> A live proving ground and safety firewall for autonomous trading agents on Bitget.
> Built on attributed open-source foundations (see [`NOTICE`](./NOTICE)); the Arena
> engine, firewall, scoring, signed ledger, live mode, and Bitget integration are original.

**Live:** https://bitarena.vercel.app (signed firewall + `/verify` + UI) · **Code:** https://github.com/Pratiikpy/agent-arena

## 1. The problem

The first generation of autonomous trading agents is here — agents that read the
market and act with no human in the loop. Two things block anyone from trusting one
with real capital:

1. **You can't tell skill from luck.** A great-looking backtest is usually a lucky
   one. Pick the best of N agents and you've probably picked the most overfit.
2. **You can't bound the downside.** An autonomous agent that misreads the market can
   place a catastrophic order before a human ever sees it.

Everyone is building agents that *generate* trades. Almost nobody is building the
layer that decides **which agents deserve to be trusted, and stops any of them from
doing something insane.**

## 2. The thesis (core logic)

**Trust is the bottleneck, and it has two halves — verification and containment.**

- **Containment:** every order from every agent must pass a single, fail-closed
  **safety firewall** that returns a signed `ALLOW` / `ALLOW_CAPPED` / `REJECT` before
  anything reaches the exchange. No agent — not even a confident LLM — can breach the
  mandate (per-order notional, total exposure, leverage, universe, trade-rate). On top of
  per-order limits, a **market-wide kill-switch** forces the *entire fleet* to de-risk-only
  in a fast crash (`FAST_RISK_OFF`). It fails closed even on malformed input, and a 23-case
  red-team battery passes **0 unsafe orders**.
- **Verification:** agents are ranked not by raw PnL but with **anti-overfitting
  statistics** — Deflated Sharpe, PSR, and the Probability of Backtest Overfitting
  (CSCV) — so a lucky winner is exposed rather than crowned. Every certificate is
  **independently verifiable** — the Verify tab checks the Ed25519 signature **in your
  browser** (Web Crypto) and pins the published issuer key, plus an offline CLI and a
  one-command whole-evidence verifier — don't trust us, check it.

We also ship concrete agents that embody testable hypotheses. The **conflict-gated
swarm** sizes by `net_signal × agreement` ("disagreement is information; size down when
analysts disagree"). The **funding-carry agent** harvests the one *structurally real*
crypto edge (perpetual funding). The Arena tests both honestly rather than asserting them.

## 3. How it works

```
perceive ─▶ decide ─▶ FIREWALL ─▶ execute ─▶ signed ledger ─▶ overfit-aware leaderboard ─▶ trust allocator
(Agent Hub   (7 agents  (signed     (Bitget /   (tamper-        (Deflated Sharpe / PBO)      (funds by
 Skills +     incl. LLM  verdict)    paper)       evident)                                     verified trust)
 technicals)  + funding)
```

- **Firewall** (`firewall/`) — Ed25519-signed certificates, fail-closed risk gates,
  ALLOW/ALLOW_CAPPED/REJECT. Verifiable offline by anyone with the embedded public key;
  benchmarks at **~0.1 ms per signed verdict** (gating every trade is effectively free).
- **Connectors** (`connectors/`) — a live Bitget v2 client (public data + HMAC-signed
  account/orders) and a deterministic paper exchange with realistic fills.
- **Competitors** (`agents/`) — conflict-gated swarm, the published-Playbook regime
  mirror, **Qwen LLM debate agent**, online Q-learning RL, momentum, buy-and-hold, and a
  **funding-carry** agent that collects real perpetual funding.
- **Perception** (`perception/`) — technicals + quant factors + the five Bitget Agent
  Hub Skills (macro / sentiment / news / on-chain / technical), with honest fallbacks.
- **Scoring** (`scoring/`) — Sharpe/Sortino/drawdown + DSR / PSR / PBO.
- **Ledger** (`ledger/`) — append-only, hash-chained, Ed25519-signed; emits the exact
  Bitget-required fields (timestamp, pair, direction, price, quantity, balance change).
- **Live mode** (`arena/live.py`) — a resumable arena that runs continuously on a
  schedule, persisting portfolios + signed ledgers + agent learning across runs (paper → live).
- **MCP + API + UI** (`mcp/`, `api/`, `web/`) — `vet_trade` over MCP or `POST /firewall`
  over HTTP returns a signed verdict; a production single-page UI (firewall / arena /
  ledger / debate / verify) is served at `/`.

**Run it** (no keys needed for the offline path; **243 tests pass**, lint-clean, 0 warnings):
```bash
cd bitarena && uv venv && uv pip install -e ".[dev,api,mcp,llm]"
uv run pytest --cov=bitarena                               # 243 passing, 92% coverage (reproducible)
uv run python scripts/run_arena.py --source bitget --instrument perp   # real-data tournament
uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 999999
uv run python scripts/llm_debate.py --symbol BTCUSDT      # Qwen debate, firewall-gated
uv run python scripts/live_step.py --symbol BTCUSDT --instrument perp  # advance the LIVE arena
uv run uvicorn bitarena.api.app:app --port 8000           # UI + API at /
```

## 4. Which tracks

One project, three tracks (eligible for all-tracks judging):

- **Trading Agent** — seven autonomous perceive→decide→execute competitors.
- **Trading Infra** — the firewall, signed ledger, overfit benchmark, independent
  verifier, and MCP server are reusable infrastructure any developer can integrate.
- **US Stock AI** — a tournament runs on Bitget tokenized US stocks (`RAAPLUSDT`).

## 5. Shipped to Bitget's own platform — four published Playbooks

Agent Arena is also a **Playbook factory**: it authors, validates, backtests, and
publishes strategies to Bitget's **GetAgent** platform (real on-platform backtests):

| Playbook | strategy_id | Sharpe | Profit factor |
|---|---|---|---|
| Adaptive Regime (Conflict-Gated, BTC) | `93af5b33-…-b653c68f6558` | 0.72 | 1.74 |
| Momentum Breakout (Donchian, BTC) | `7f86f156-…-731da4e3ec4f` | 1.68 | 2.33 |
| Momentum Breakout (Donchian, ETH) | `849d200f-…-708a472556d5` | 0.58 | 1.42 |
| Adaptive Regime (Conflict-Gated, ETH) | `1fb29226-…-9a18a03ee539` | 2.15 | 3.34 |

(The ETH regime has the best risk-adjusted ratios but a near-flat absolute return — the
conflict-gate kept it highly selective; see [`playbook/PUBLISHED.md`](./playbook/PUBLISHED.md).)
Three more (a mean-reversion strategy, plus both the breakout and the regime strategy on SOL) were backtested and
**deliberately withheld for underperforming on real data** — we publish only when the
evidence earns it. See [`playbook/PUBLISHED.md`](./playbook/PUBLISHED.md).

## Verifiable usage records

All under [`evidence/`](./evidence/README.md), reproducible with the commands above:

- `bitget_btc_perp/`, `bitget_eth_perp/`, `bitget_sol_perp/` — tournaments on **real
  Bitget perps** (1-hour candles), each including the funding-carry competitor with real
  funding settled to equity.
- `bitget_tokenized_aapl/` — tournament on **real Bitget tokenized AAPL** (Track 3).
- `firewall_demos.json` — ALLOW / ALLOW_CAPPED / REJECT + tamper-detection proof.
- `firewall_bench.json` — ~0.1 ms per signed verdict (~9,700/sec single core).
- `funding_carry.json`, `funding_edge_walkforward.json` — the funding edge validated with
  walk-forward + Deflated Sharpe (modest real carry + downside-avoidance; beats buy-hold in
  4/5 real-BTC folds, driven mainly by staying defensive — carry and price-PnL reported separately).
- `walk_forward.json`, `swarm_edge.json` — agent stability + the swarm thesis tested honestly.
- `overfit_trap.json` — the *verification* half quantified: on a no-edge market, DSR + PBO flag
  naive best-of-N selection as overfit (PBO 0.91) before any capital is risked.
- `llm_debate.json` — a live Qwen debate, gated by the firewall.
- `redteam.json` — 20 adversarial attacks + 3 controls; **0 unsafe orders passed**, signed.
- `firewall_value.json` — the firewall's *containment value* quantified: a misbehaving agent
  stays **solvent under the mandate** vs **bankrupt unprotected** ($8,574 saved on a $10k account).
- `external_agent_session.json` — a third-party bot vetting every trade over HTTP (Track-2).
- `allocator.json` — the TrustAllocator funding agents by verified performance.

Each tournament folder has `leaderboard.json`, per-agent `trades_*.csv` (Bitget-required
fields), and signed `ledgers/*.jsonl`.

## Honest self-assessment

**What is genuinely strong**
- The firewall is real, live, signed, and **independently verifiable** — a judge can
  `curl` a verdict in seconds, and mutating any field invalidates the certificate. The
  four core mechanisms (firewall, ledger, scoring, accounting) are **property-tested over
  thousands of randomized inputs**; the red-team proves 0 unsafe orders pass.
- The one real edge, made live: the **funding-carry agent** collects real perpetual
  funding (modest — ~0.03%/fold of harvested carry) and stays defensive; it ranks
  consistently top-3 by Sharpe across BTC/ETH/SOL and beats buy-hold in 4/5 walk-forward
  folds — driven *mainly by downside-avoidance, not carry income* (we report both
  separately). It's a live, correctly-accounted arena competitor.
- Four strategies **published on Bitget's GetAgent platform** with real backtests.
- The scoring tells the truth: with the full roster the synthetic run reports `PBO ≈ 0.84`
  (the in-sample winner is mostly luck), the regime scenario `PBO ≈ 0.00` (robust ranking).

**What is honestly limited (and reported, not hidden)**
- No *price-directional* agent reliably beats buy-and-hold on flat real data — active
  trading does not manufacture edge from noise, and the Arena says so. The exception is
  the structural funding edge. The headline product is the *trust layer*.
- The conflict-gated swarm beats the naive momentum baseline **only in the choppy regimes
  it targets** (regime scenario: swarm −1.8% in 50 trades vs momentum −3.6% in 109) —
  exactly its design claim; over random-walk chop the edge is directional but not
  statistically significant, and we report that.
- The Agent Hub signals are honest offline proxies (live Skill briefs replace them);
  live order placement needs a Bitget key with trade permission.

## What only an AI agent can do here

The competitors read several analyst perspectives, debate them (the LLM agent literally
argues bull vs bear and down-weights disagreement), size by conviction, and self-grade —
continuously, with no human. The Arena is the harness that makes a fleet of such agents
*safe to run and honest to compare*.

## Where this goes (room to grow)

Each next step is an extension of what already ships, not a rewrite:

- **Paper → real-money, same gate.** The Bitget connector already HMAC-signs orders, so placing
  a real dust-sized order on a trade-permission sub-account flips the arena from paper to live
  with *no change to the firewall* — every real order is gated and signed exactly as paper ones
  are (`connectors/bitget/client.py`, `arena/live.py`).
- **Firewall-as-a-service.** The signed-cert HTTP API + `FirewallClient` SDK + MCP server are the
  foundation for a hosted, multi-tenant firewall any agent platform integrates; the `Mandate`
  becomes a per-tenant, user-parameterized contract.
- **Deeper verification.** The overfit suite (DSR / PSR / PBO) extends to data-snooping and
  regime-stability certificates — the firewall could certify *"evaluated without lookahead,"* a
  claim competitors rarely make (`scoring/overfit.py`).
- **A trust-allocator funding a live fleet.** `TrustAllocator` already routes capital by
  *verified* performance; pointed at a running fleet it becomes continuous allocation under
  containment (`arena/allocator.py`).
- **Richer market structure.** Queue-position limit fills, multi-venue quotes, and options/perp
  funding plug into the existing fill model and connector protocol.

The thesis scales the way it starts: more agents, more capital, more markets — all behind one
signed, verifiable safety gate.
