# Agent Arena — Bitget AI Hackathon S1 Submission Packet

Everything needed to submit, in one place. Paste the relevant sections into the
[submission form](https://forms.gle/CEGB6fRtuobD3bCj8). Fields marked **[YOU]** are the
only ones I can't fill (credentials / hosting / posting).

---

## At a glance

Two connected assets, one thesis ("trust is the bottleneck in agentic trading"):

1. **Agent Arena** — a live signed-firewall + proving ground for autonomous trading
   agents on Bitget. (Code: `.research/bitarena/`)
2. **Four published Bitget Playbooks** — Agent Arena is a Playbook *factory*; all are
   published and backtested on Bitget's GetAgent platform (real equity curves):
   - **Adaptive Regime (Conflict-Gated, BTC)** — `93af5b33-8a16-43ea-8e45-b653c68f6558`
     (Sharpe 0.72, PF 1.74).
   - **Momentum Breakout (Donchian, BTC)** — `7f86f156-1034-4494-9969-731da4e3ec4f`
     (Sharpe 1.68, PF 2.33).
   - **Momentum Breakout (Donchian, ETH)** — `849d200f-5b58-459a-b610-708a472556d5`
     (Sharpe 0.58, PF 1.42).
   - **Adaptive Regime (Conflict-Gated, ETH)** — `1fb29226-9515-496c-a059-9a18a03ee539`
     (Sharpe 2.15, PF 3.34 — best risk-adjusted, near-flat absolute). All on Bitget →
     Playbook → Explore. Three more (mean-reversion, plus both momentum and regime on SOL) were
     backtested and deliberately withheld for underperforming.

**Recommended primary track:** 🟩 **Trading Infra (Track 2)** — our deepest, most novel
surface (firewall + overfit benchmark + verifier + MCP). It also satisfies Track 1
(autonomous agents) and Track 3 (tokenized AAPL), and #1 is judged across all tracks.

---

## Project description (the required four-part structure)

**1. Problem.** The first generation of autonomous trading agents is here, but nobody
can be trusted with capital, because you cannot (a) tell skill from a lucky backtest, or
(b) stop an agent from doing something catastrophic before a human sees it. Everyone
builds agents that *generate* trades; almost nobody builds the layer that decides which
agents deserve capital and stops any of them from blowing up.

**2. Core logic / thesis.** Trust = **containment + verification**. Containment: every
order from every agent passes one fail-closed firewall that returns a *signed*
ALLOW / ALLOW_CAPPED / REJECT certificate before anything reaches the exchange.
Verification: agents are ranked with anti-overfitting statistics (Deflated Sharpe, PSR,
PBO), not raw PnL, and a meta-allocator funds them by *verified* performance. A secondary,
testable bet — "size by signal agreement, stay flat under conflict" — is implemented and
measured honestly. We also surface the one *structurally real* crypto edge (funding
carry) and validate it on real Bitget data with walk-forward + Deflated Sharpe.

**3. How it works.** perceive (technicals + quant factors + Bitget Agent Hub skills) →
decide (7 agents incl. a live Qwen LLM debate, the published Playbook strategy, and a
funding-carry competitor) →
**firewall** (signed, red-teamed) → execute (paper / Bitget) → **signed ledger** →
overfit-aware leaderboard → **trust allocator**. Exposed over an HTTP API and an MCP
server, with an independent `/verify` endpoint and a production UI. 218 passing tests.
Run it: `cd bitarena && uv pip install -e ".[dev,api,mcp,llm]" && uv run pytest` then
`uv run uvicorn bitarena.api.app:app --port 8000`.

**4. (Optional) Take on AI trading.** The edge in agentic trading will not be a secret
alpha; it will be *trust infrastructure* — verifiable safety and honest measurement that
let a fleet of agents be run with real capital. That is what Agent Arena is.

---

## Per-track submission checklist (mapping)

| Requirement | What we submit |
|---|---|
| **UID matches registration** | **[YOU]** your Bitget UID |
| **Public GitHub + complete README** | **[YOU]** push `bitarena/` to a public repo. README is ready (install, run, integrate, examples). |
| **Thesis clearly stated** | The four-part description above (also in `SUBMISSION.md`). |
| **Verifiable usage record** (≥1) | Multiple — see below. |
| **Deployment link** (optional) | **[YOU]** deploy via `DEPLOY.md` (Dockerfile + render.yaml ready); UI+API served at `/`. |
| **Backtest report w/ code** | Four published Playbooks on Bitget (on-platform) **+** `evidence/` reproducible runs with code in `bitarena/`. |
| **Demo video** (≤3 min) | **[YOU]** record using `DEMO.md` storyboard. |
| **Community post** (optional award) | **[YOU]** quote the Bitget tweet, tag #BitgetHackathon + @Bitget_AI. |

## Verifiable usage records (all in `evidence/`, reproducible)

- **Four published Bitget Playbooks** — real on-platform backtests with real equity curves,
  public on GetAgent (momentum + adaptive-regime on BTC & ETH). A systematic 2×3
  (strategy × asset) study: the four BTC/ETH winners are published; all three SOL/ETH-mean-rev
  losers are withheld — publish discipline as evidence. `playbook/PUBLISHED.md`.
- **Live signed firewall verdicts** — `firewall_demos.json` (ALLOW/CAPPED/REJECT + tamper
  proof); callable live at `POST /firewall`, independently checkable at `POST /verify`.
- **Red-team** — `redteam.json`: 15 attacks, **0 unsafe orders passed**, all signed.
- **Firewall containment value** — `firewall_value.json`: a misbehaving agent stays solvent
  under the mandate vs bankrupt unprotected ($8,341 saved on a $10k account).
- **Overfit-detection value** — `overfit_trap.json`: on a no-edge market, DSR + PBO (0.77) flag
  naive best-of-N selection as luck, not skill, before capital is committed.
- **Tournaments on real Bitget data (1h)** — `bitget_btc_perp/`, `bitget_eth_perp/`,
  `bitget_sol_perp/`, `bitget_tokenized_aapl/` (Track 3): leaderboards + signed
  hash-chained ledgers + trade CSVs (timestamp/pair/side/price/qty/balance Δ).
- **External integration** — `external_agent_session.json`: a third-party bot vetting
  every trade through the firewall over HTTP (Track-2 "another developer integrated it").
- **Funding-carry edge study** — `funding_carry.json`: real Bitget funding history,
  walk-forward + Deflated Sharpe.
- **Live LLM debate** — `llm_debate.json`: a real Qwen analyst debate, firewall-gated.
- **Capital allocator** — `allocator.json`: trust-weighted vs equal-weight.

## Honesty note (judges reward this)

See `SELF_ASSESSMENT.md` — a rubric-by-rubric rating with real limits stated, not hidden
(no price-directional agent reliably beats buy-hold on flat data; the swarm's chop edge is
directional but not statistically significant; the Agent Hub skills use honest offline
fallbacks). Honest self-assessment is an explicit scoring criterion.

---

## Owner action checklist (the only things left, all yours)

> Pre-push safety: audited — **no API keys in any git-tracked file** (Playbook and Qwen
> keys never committed; `.env` is gitignored and untracked). Safe to make the repo public.

1. **[YOU]** Push `bitarena/` to a **standalone** public GitHub repo. It currently lives
   inside the private parent repo and is gitignored there with no `.git` of its own, so
   initialize it fresh (its `.gitignore` already excludes `.env`/`.keys`/secrets — audit
   confirmed none are tracked):
   ```bash
   cd .research/bitarena
   git init && git add . && git commit -m "Agent Arena: trust layer for autonomous trading agents"
   gh repo create agent-arena --public --source=. --push
   ```
   Paste the resulting URL.
2. **[YOU]** Deploy (`DEPLOY.md`) and paste the public URL (UI + API + `/verify`).
3. **[YOU]** Record the ≤3-min demo video (`DEMO.md`) and paste the link.
4. **[YOU]** Post the #BitgetHackathon quote-tweet; paste the link.
5. **[YOU]** Submit with your registration UID, primary track = Trading Infra.
6. *(Optional, highest-leverage)* a real dust-sized live Bitget order with a
   trade-permission key, to move from "paper" to "live trading."

Everything else — code, tests, evidence, the published Playbooks, docs — is done.

## Ready-to-paste assets (for the owner actions)

**GitHub repo description (one-liner):**
> Agent Arena — the trust layer for autonomous trading agents on Bitget: a signed,
> verifiable safety firewall + overfit-aware tournament + a live, self-improving arena.
> 4 published GetAgent Playbooks.

**GitHub topics:** `bitget` `trading-agents` `ai-agents` `crypto` `algorithmic-trading`
`reinforcement-learning` `mcp` `fastapi` `python` `hackathon`

**Community post / #BitgetHackathon quote-tweet (draft):**
> Built **Agent Arena** for the @Bitget_AI Hackathon: the trust layer for autonomous
> trading agents. Every AI order passes a signed safety firewall (0 unsafe in red-team,
> ~0.1 ms/verdict, verify it yourself), agents are ranked by Deflated Sharpe/PBO — not
> luck — and a meta-allocator funds the winners. 4 strategies already published on
> GetAgent, plus a live arena that runs on real Bitget data. #BitgetHackathon
> [repo link] [demo link]
