# Evidence

Reproducible artifacts for the Agent Arena. The whole point of the Arena is to
measure agents *honestly* — so this folder reports what actually happened, including
where the headline "swarm" agent does **not** win.

## How to reproduce

```bash
uv run python scripts/make_evidence.py                       # firewall demos + synthetic + regime (offline, deterministic)
uv run python scripts/run_arena.py --source bitget \
    --symbol BTCUSDT --instrument perp --bars 1000 \
    --out evidence/bitget_btc_perp                           # real Bitget market data
uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 999999
```

## What's here

| Path | What it is |
|---|---|
| `firewall_demos.json` | One ALLOW, one ALLOW_CAPPED, one REJECT verdict — each with an Ed25519-signed certificate — plus a tamper-detection proof |
| `synthetic_run/` | Deterministic tournament on a synthetic price path (leaderboard + per-agent signed trade CSVs + JSONL ledgers) |
| `regime_scenario/` | Tournament on a constructed trend → chop → trend market |
| `bitget_btc_perp/` | Tournament on **real Bitget BTCUSDT perp** 1-hour candles, with a **funding-carry** agent harvesting real perpetual funding (settlements credited to equity) |
| `bitget_eth_perp/`, `bitget_sol_perp/` | More real-Bitget perp tournaments (breadth) |
| `bitget_tokenized_aapl/` | Tournament on **real Bitget tokenized AAPL** (`RAAPLUSDT`) — Track 3 (full signed ledgers) |
| `tokenized_stock_sweep.json` | **Track 3 breadth:** the arena + firewall across **six** real Bitget tokenized US stocks (AAPL, TSLA, NVDA, MSFT, GOOGL, META) — 883 firewall intents, **0 unsafe**, all ledgers verified |
| `last_run/` | Working copy of the most recent tournament — what the API serves at `GET /leaderboard` (and the deployed UI reads) |
| `redteam.json` | 20 adversarial attacks + 3 controls; **0 unsafe orders passed**, all signed |
| `firewall_value.json` | The firewall's *containment value*, quantified: a misbehaving agent (8×-oversized orders) on an adverse market stays **solvent (+\$4,212)** under the mandate vs **bankrupt (−\$4,362)** unprotected — the firewall saved \$8,574 on a \$10k account |
| `regime_killswitch.json` | The firewall's *market-wide* kill-switch: a reckless "buy the dip" agent through a ~16% flash crash, run with the kill-switch ON vs OFF. In `FAST_RISK_OFF` the firewall blocks new exposure (signed REJECTs, issuer `98683e5c`) while still permitting de-risking — the protected fleet avoids **\$3,120** of further loss vs unprotected (on a \$100k account). Per-order safety + fleet-wide circuit-breaker. |
| `firewall_bench.json` | Firewall latency: a full signed verdict (gates + Ed25519) is **~0.1 ms** (~9,700/sec single core) — gating every trade is effectively free |
| `external_agent_session.json` | A third-party bot vetting every trade through the firewall over HTTP |
| `llm_debate.json` | One live Qwen analyst debate, gated by the firewall |
| `allocator.json` | TrustAllocator vs equal-weight: capital flows to verified performers, decayers starved |
| `funding_carry.json` | Funding-carry edge study on **real Bitget funding history** (passive + adaptive sweep, walk-forward, Deflated Sharpe) |
| `playbook_backtests.json` | The Playbook factory's **on-platform GetAgent backtests** — a systematic 2×3 study (4 published, 3 withheld) with the publish/withhold decision per strategy |
| `walk_forward.json` | Agents across disjoint real-Bitget folds: per-fold return + cross-window stability (consistency, % positive folds) |
| `swarm_edge.json` | Bootstrap test of the conflict-gated swarm vs momentum over 80 choppy scenarios: directionally positive (wins 59%, +0.90% mean) but **not statistically significant** (95% CI straddles 0) — the secondary thesis held to the same rigor, reported honestly |
| `overfit_trap.json` | The *verification value*: on a no-edge random walk, naively crowning the in-sample best agent is overfit (**PBO 0.91**); the Deflated Sharpe + PBO flag it as luck before capital is risked — the agents don't manufacture edge from noise |
| `funding_edge_walkforward.json` | The funding-carry agent vs buy-hold across disjoint real-BTC-perp folds, with the two effects reported **separately and honestly**: (1) harvested funding is real but **small** (~$2–3/fold, ≈0.03%); (2) the agent **avoids drawdowns** by staying defensive, and *that* drives the +3.59% mean excess (beats buy-hold in 4/5 folds — e.g. +14.4% in the −9% fold by being nearly flat, and fold 4 won having collected $0 funding). Honest read: the structural edge is *modest carry income*; the buy-hold outperformance here is mostly *downside avoidance*, not carry. |

Each tournament folder has `leaderboard.json` (full result, incl. firewall stats and
PBO), `trades_<agent>.csv` (Bitget-required fields: timestamp, pair, direction,
price, quantity, balance change), and `ledgers/<agent>.jsonl` (the signed,
hash-chained records — run `verify()` to confirm integrity).

## Honest results

**The firewall works and is verifiable.** `firewall_demos.json` shows all three
verdict types with signed certificates, and that mutating any signed field flips
`certificate_valid` to `false` (tamper detection).

**The thesis holds in the regime it targets — and only there.** In the regime
scenario (trend → chop → trend):

| agent | final equity | trades | note |
|---|---|---|---|
| benchmark-buyhold | ~$11,557 | 4 | passive wins when the market simply trends |
| persona-team | ~$9,952 | 65 | bull/bear/quant ensemble, risk-vetoed |
| **swarm (conflict-gated)** | **~$9,824** | **50** | flattened through the choppy middle — few trades |
| rl-qlearn | ~$9,658 | 140 | online learner; explores a lot |
| baseline-momentum | ~$9,640 | 109 | whipsawed in the chop — most trades, worst result |
| regime | ~$9,077 | 125 | the published-Playbook mirror; underperforms in chop |

The swarm beats the naive momentum baseline (−1.8% vs −3.6%) with **~half the trades**, which
is exactly its design claim: *when signals disagree (chop), size down; momentum keeps trading
and bleeds.* Buy-and-hold still wins overall because the scenario is trend-dominated — and the
Arena reports that rather than hiding it.

**On flat real data, nobody beats breakeven — and that's reported, not hidden.** On a
~16h real Bitget BTC perp window all agents hovered near flat (see
`bitget_btc_perp/leaderboard.json`). Active trading does not manufacture edge from
noise, and the Arena says so.

**Overfitting is flagged — and the metric discriminates.** On the synthetic run's six agents
(the funding-carry competitor only joins on real perp data, where funding exists) the
cross-agent `PBO ≈ 0.84` is high (the in-sample winner there is mostly luck), while the regime
scenario reports `PBO ≈ 0.00` (the ranking is robust). Same metric, opposite verdicts — that is the number that stops a lucky
backtest from being sold as an edge. (The `RegimeAgent` — the published Bitget Playbook
mirror — wins the clean synthetic trend but underperforms in chop and on flat real data,
reported honestly rather than hidden.)

## The one real edge (funding carry), reported honestly

`funding_carry.json` studies a delta-neutral funding carry on **real Bitget funding
history** (~90 days, 270 intervals). The finding is honest: carry is a real but
**modest, low-risk, regime-dependent** yield — e.g. ETHUSDT ~+3% annualized passive
at a very high Sharpe (~12) with <0.2% drawdown (high Sharpe reflects funding's low
variance, not big returns), SOL mildly positive, and BTC's passive carry slightly
negative over this window (skipping negative-funding intervals flips it positive).
This is the genuine structural edge — small, steady, and validated with walk-forward
and a Deflated Sharpe, not an overfit backtest.

**It is now a live arena competitor.** The `funding-carry` agent harvests this edge in
the tournament (funding settled to equity each interval, `Portfolio.apply_funding`). On
real perp data it is **consistently top-3 by Sharpe across BTC/ETH/SOL** while collecting
real positive carry (BTC #1 / +$8.35, SOL #2 / +$16.19, ETH #3 / +$14.82). Honest scope:
a single-instrument perp agent bears directional price risk (it can't be delta-neutral),
so this blends carry income with price PnL — the arena reports both.

## The takeaway

The product is not "an agent that always wins." It is the **trust layer**: a live,
signed safety firewall that no agent can bypass, plus overfit-aware scoring that tells
you which agents actually deserve capital. The evidence above is the Arena doing that
job — honestly.
