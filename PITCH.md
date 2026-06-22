# Agent Arena — the trust layer for autonomous trading agents

> A live, signed safety firewall and proving ground that decides which AI trading
> agents deserve capital — and stops any of them from blowing up. Built on Bitget.

**▶ Live:** [bitarena.vercel.app](https://bitarena.vercel.app) · **Code:** [github.com/narutopyy/agent-arena](https://github.com/narutopyy/agent-arena)

## The problem
The first generation of autonomous trading agents is here. Nobody can hand one real
capital, because you can't (1) tell skill from a lucky backtest, or (2) stop an agent
from doing something catastrophic before a human ever sees it. Everyone builds agents
that *generate* trades. **Almost nobody builds the layer that makes them trustworthy.**

## The insight
A fleet of autonomous agents is only safe to run if something physically caps the downside.
That is the unlock. Give each agent a hard safety boundary and it can run fully unsupervised,
so the agents end up **more** autonomous, not less. Trust is the enabler of autonomy, not a
limit on it. Two parts make it work.
- **Containment, the enabler.** Every order from every agent passes one fail-closed firewall
  that returns a cryptographically signed ALLOW / ALLOW_CAPPED / REJECT before anything reaches
  the exchange. No agent can breach its mandate, and a market-wide **kill-switch** flattens the
  whole fleet in a fast crash. Because the blast radius is capped, an agent can decide end to
  end with no human in the loop.
- **Verification, the honesty.** Agents are ranked by skill that survives an overfit test
  (Deflated Sharpe, PBO), not raw PnL, and a meta-allocator funds them by verified skill.
  Anyone can check a certificate **in their own browser** (Web Crypto), pinned to our published
  key. You do not trust us, you check.

## What it is
**Agent Arena**: a live tournament where multiple autonomous agents (a conflict-gated
swarm, a Qwen LLM debate team, an RL agent, the published Playbook strategy, momentum,
buy-hold) trade Bitget under the firewall, are scored for skill-vs-luck, and are funded
by a trust allocator. Plus a **Playbook factory** that ships validated strategies to
Bitget's own GetAgent platform.

## Proof it's real (not slides)
- **Live signed firewall** — curl a verdict in 10 seconds; tamper any field and the
  signature dies. A 25-case red-team battery: **0 unsafe orders ever passed.**
- **It makes money — four published Bitget Playbooks** that profit on real on-platform
  backtests: **profit factors 1.42–3.34** (BTC breakout wins **2.33×** its losses — **+0.40% on a
  0.26% drawdown** account-basis, ≈+39.7% on the deployed $1k budget; both bases shown so the
  number can't mislead) across the set (ETH breakout 1.42, adaptive regime BTC 1.74, adaptive
  regime ETH Sharpe 2.15 / PF 3.34) — plus three more honestly *withheld* because they underperformed.
- **A real, structural money edge, honestly validated** — funding carry on real Bitget funding
  history (walk-forward + Deflated Sharpe). The delta-neutral *carry study* returns **~+3.1%
  annualized** at low risk on BTC (adaptive — skipping negative-funding intervals; the high Sharpe
  reflects funding's low variance, not big returns); the live arena's funding-carry agent is
  single-instrument, so it harvests that carry **while bearing price risk**, and ranks top-3 by
  Sharpe across BTC/ETH/SOL. On flat price data no agent beats buy-hold, and we report that — the
  returns are structural, never cherry-picked.
- **Independently verifiable, even in your browser** — the Verify tab checks the Ed25519
  signature client-side (Web Crypto) and pins the published issuer; plus a signed
  hash-chained ledger, an offline CLI, and a one-command whole-evidence verifier.
- **Effectively free** — a full signed verdict (all gates + Ed25519) takes **~0.1 ms**
  (~9,700 verdicts/sec, single core): gating every trade is production-cheap.
- **337 passing tests**, lint-clean, real Bitget data across BTC/ETH/SOL perps **plus six
  tokenized US stocks** (AAPL/TSLA/NVDA/MSFT/GOOGL/META).

## Why only an AI agent can do this
The agents do what only an LLM agent can. They weigh several analyst views (macro, sentiment,
news, on-chain, technical), argue them bull versus bear, down-weight their own disagreement,
size by conviction, and act, continuously, with no human. A rules engine cannot read conflicting
narratives in natural language and change its mind. The firewall and the overfit-aware tournament
are what make running a whole fleet of these agents safe to deploy and honest to compare. Trust
is not a guardrail on autonomy here. It is the thing that makes full autonomy fundable.

## Tracks (all three)
Trading Agent (the autonomous agents) · Trading Infra (firewall, benchmark, MCP server,
verifier, SDK) · US Stock AI (the arena + firewall across six tokenized US stocks).

## Status
Code, tests, evidence, four published Playbooks, the production UI, and a **live public deploy
at [bitarena.vercel.app](https://bitarena.vercel.app)** are done — a fresh signed verdict on the
live BTC price ticks on the landing page right now. What's honestly left: a ≤3-min demo video
(`make showcase` stands in) and a real dust-sized live order (gated tooling ready).

*The edge in agentic trading won't be a secret alpha — it will be trust infrastructure.
That's what we built.*
