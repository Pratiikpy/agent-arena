# Agent Arena — the trust layer for autonomous trading agents

> A live, signed safety firewall and proving ground that decides which AI trading
> agents deserve capital — and stops any of them from blowing up. Built on Bitget.

**▶ Live:** [bitarena.vercel.app](https://bitarena.vercel.app) · **Code:** [github.com/Pratiikpy/agent-arena](https://github.com/Pratiikpy/agent-arena)

## The problem
The first generation of autonomous trading agents is here. Nobody can hand one real
capital, because you can't (1) tell skill from a lucky backtest, or (2) stop an agent
from doing something catastrophic before a human ever sees it. Everyone builds agents
that *generate* trades. **Almost nobody builds the layer that makes them trustworthy.**

## The insight
Trust = **containment + verification**.
- **Containment** — every order from every agent passes one fail-closed firewall that
  returns a *cryptographically signed* ALLOW / ALLOW_CAPPED / REJECT before anything
  reaches the exchange. No agent can breach its mandate, and a market-wide **kill-switch**
  force-flats the whole fleet in a fast crash.
- **Verification** — agents are ranked with anti-overfitting math (Deflated Sharpe, PBO),
  not raw PnL, and a meta-allocator funds them by *proven* trust. Anyone can verify a
  certificate — **in their own browser** (Web Crypto), pinned to our published key. You
  don't have to trust us.

## What it is
**Agent Arena**: a live tournament where multiple autonomous agents (a conflict-gated
swarm, a Qwen LLM debate team, an RL agent, the published Playbook strategy, momentum,
buy-hold) trade Bitget under the firewall, are scored for skill-vs-luck, and are funded
by a trust allocator. Plus a **Playbook factory** that ships validated strategies to
Bitget's own GetAgent platform.

## Proof it's real (not slides)
- **Live signed firewall** — curl a verdict in 10 seconds; tamper any field and the
  signature dies. A 23-case red-team battery: **0 unsafe orders ever passed.**
- **Four published Bitget Playbooks** with real on-platform backtests (BTC breakout
  Sharpe 1.68 / PF 2.33, ETH breakout PF 1.42, adaptive regime BTC PF 1.74, adaptive regime
  ETH Sharpe 2.15 / PF 3.34) — plus three more honestly *withheld* because they underperformed.
- **One real, structural edge, honestly validated** — funding carry on real Bitget
  funding history (walk-forward + Deflated Sharpe): modest, low-risk, regime-dependent.
- **Independently verifiable, even in your browser** — the Verify tab checks the Ed25519
  signature client-side (Web Crypto) and pins the published issuer; plus a signed
  hash-chained ledger, an offline CLI, and a one-command whole-evidence verifier.
- **Effectively free** — a full signed verdict (all gates + Ed25519) takes **~0.1 ms**
  (~9,700 verdicts/sec, single core): gating every trade is production-cheap.
- **247 passing tests**, lint-clean, real Bitget data across BTC/ETH/SOL perps **plus six
  tokenized US stocks** (AAPL/TSLA/NVDA/MSFT/GOOGL/META).

## Why only an AI agent can do this
The competitors read five analyst perspectives, debate them (the LLM agent argues bull
vs bear and *down-weights disagreement*), size by conviction, and self-grade —
continuously, with no human. Agent Arena is the harness that makes a fleet of such
agents safe to run and honest to compare.

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
