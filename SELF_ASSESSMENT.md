# Honest Self-Assessment

Bitget's judging explicitly values *"honest self-assessment over exaggeration."* So
here is Agent Arena rated against each dimension — strengths **and** real limits.

## Scorecard

| Dimension | Self-rating | One-line |
|---|---|---|
| Depth of thesis | 9/10 | Trust = containment + verification; a testable conflict-gating bet; one real (funding) edge, now live in the arena |
| Runnability | 8/10 | Live deploy with a ticking `/pulse` heartbeat + a real `/live` tournament, real Bitget data, four Playbooks, 253 tests — a gated real-money order is one command away (needs a trade key) |
| Completeness | 9/10 | End-to-end loop, 7 agents, allocator, signed ledger, market kill-switch, in-browser verify, client SDK + MCP, live UI, four Playbooks |
| Novelty & potential | 9/10 | Agent-vs-agent arena + signed firewall (issuer-pinned, fleet kill-switch) + trust-allocator + overfit scoring + live LLM debate + browser-side verification |
| Bitget-native depth | 8/10 | Real public data, **four published GetAgent Playbooks**, live Qwen, tokenized-stock Track 3 |

## Depth of thesis — strong
The core bet is that the bottleneck in agentic trading is **trust, not alpha**:
containment (a signed firewall no agent can bypass) plus verification (overfit-aware
scoring + an independent verifier). The secondary bet — "size by agreement, stay flat
under conflict" — is implemented and tested. **Limit:** the conflict-gated swarm only
beats the naive baseline in the regimes it targets, and no *price-directional* agent
reliably beats buy-hold on flat data — we report that. The exception is the structural
edge: the funding-carry agent collects real perpetual funding and ranks consistently
top-3 by Sharpe across BTC/ETH/SOL.

## Runnability — strong, with a clear ceiling
Live signed firewall at **https://bitarena.vercel.app** (also curl-able offline), with a
**continuously-ticking `/pulse` heartbeat** — a fresh Ed25519-signed verdict on the live BTC
price every few seconds — and a **real, signed `/live` tournament** served from the deploy.
Real Bitget market data, **four published GetAgent Playbooks**, a live Qwen debate agent, and
253 passing offline tests; the public repo (CI green) and the deploy are both up. **The paper →
live step is one gated command** — `scripts/place_live_order.py --confirm` places only the
firewall-ALLOWed size and writes a signed receipt. **Limit:** trading is still paper (the real
order needs a trade-permission key + a go-ahead), and the ≤3-min demo video is not yet recorded
(storyboard ready; `make showcase` is a runnable stand-in).

## Completeness — strong
Full perceive → decide → firewall → execute → signed ledger → leaderboard → trust-
allocate loop; seven competitor agents (incl. the published-Playbook regime mirror, a
funding-carry agent, and an optional live LLM); MCP server + HTTP API + independent
verifier; the production UI; a reproducible evidence pack. In **live mode** the Q-learning
agent now compounds its learning across runs (its Q-table is persisted), and the arena
resumes state between scheduled invocations. The firewall also gained a **market-wide
kill-switch** (forces the fleet de-risk-only in a fast crash), **issuer-pinned + in-browser
(Web Crypto) certificate verification**, a `FirewallClient` SDK, and a one-command
whole-evidence verifier; the deterministic evidence is reproducible and idempotent. **Limit:**
Agent Hub Skills run as honest offline fallbacks (not live calls), and the other agents are
deterministic functions of market history by design (no cross-run learning).

*Precise scope of "no agent can bypass":* the firewall is the **single execution chokepoint**
every order the arena places passes through, and the only shipped integration surface (the
HTTP API / MCP `vet_trade`) is the gated one — there is no ungated path exposed to an agent.
This is an architectural guarantee enforced by that one code path, not an OS-level process
sandbox; it bounds what an agent's *decisions* can do, which is the threat model.

## Novelty — strong
A live agent-vs-agent trading arena where every order is gated by an **issuer-pinned signed
certificate** (verifiable in your own browser, no server), a **fleet-wide kill-switch**
force-flats every agent in a crash, agents are ranked with Deflated Sharpe / PBO, and a
meta-allocator funds them by verified trust — none of that exists in the OSS field we surveyed.
**Limit:** the deploy runs a continuous signed `/pulse` heartbeat on live data and serves a real
`/live` tournament, but the per-tick arena replays 1h bars rather than live order flow — a
faithful harness, not yet tick-level live execution.

## Bitget-native depth — strong
Real Bitget v2 public data (verified live), **four Playbooks published on Bitget's own
GetAgent platform** (real Sharpe/curves; a systematic 2×3 study, four winners published and
three losers withheld), Qwen via the hackathon proxy, a tokenized-US-stock competitor
(Track 3, `RAAPLUSDT`), and an authenticated-key code path. **Limit:**
live Skill Hub calls and a real dust order remain to be wired.

## Track coverage (all three)
- **Track 1 — Trading Agent:** seven autonomous perceive→decide→execute agents (incl. a funding-carry competitor).
- **Track 2 — Trading Infra:** the firewall, signed ledger, overfit benchmark, MCP
  server, HTTP API, and independent verifier — reusable by any developer.
- **Track 3 — US Stock AI:** a tournament on Bitget tokenized AAPL.

## What would move every number up (the remaining owner actions)
The public repo and live deploy are already up. What remains: post the ≤3-min demo video
(or show `make showcase`), place one real dust-sized Bitget order — **the gated tooling is
ready** (`scripts/place_live_order.py --confirm`); it only needs a trade-permission key — and
wire one live Agent Hub Skill. The engineering for all of these is in place; what remains is
recording, a trade key, and the post.
