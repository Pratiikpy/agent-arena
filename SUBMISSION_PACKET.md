# Agent Arena — Bitget AI Hackathon S1 Submission Packet

Everything needed to submit, in one place. Fields marked **[YOU]** are the only ones I can't
fill (credentials / hosting / posting).

> ⚠️ **DQ-CRITICAL — verify the form URL first.** The official Base Camp doc lists **two
> different** submission forms: `forms.gle/CEGB6fRtuobD3bCj8` (Requirements section) and
> `forms.gle/mGrppbHw6gz5jmot8` (Resources table). They differ. **Confirm which is live before
> submitting** — submitting to the wrong/closed form means *not submitted = disqualified*. Also
> baseline-or-DQ: your **UID must match registration**, and **all links public / no login**
> (GitHub ✓, deploy ✓ no-login).
>
> ⚠️ **Demo video — sources conflict, so don't assume it's optional.** The per-track summary says
> the video is optional unless the demo needs a login (ours doesn't), but a Track-2-specific line
> says *required*. Safe path: **record the ≤3-min `DEMO.md` video** OR submit **primary = Track 1
> or Track 3** (video is explicitly optional there, and #1 is judged across all tracks anyway).
> Do NOT submit primary=Track 2 with no video on the "no-login → optional" assumption.

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
server, with an independent `/verify` endpoint and a production UI. 265 passing tests.
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
| **Public GitHub + complete README** | ✅ **Live:** https://github.com/Pratiikpy/agent-arena (public, CI green, v0.1.0). README has install/run/integrate/examples. |
| **Thesis clearly stated** | The four-part description above (also in `SUBMISSION.md`). |
| **Verifiable usage record** (≥1) | Multiple — see below. |
| **Deployment link** (optional) | ✅ **Live:** https://bitarena.vercel.app — UI + signed firewall + `/verify`, callable now. |
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
- **Red-team** — `redteam.json`: 21 attacks, **0 unsafe orders passed**, all signed.
- **Firewall containment value** — `firewall_value.json`: a misbehaving agent stays solvent
  under the mandate vs bankrupt unprotected ($8,574 saved on a $10k account).
- **Overfit-detection value** — `overfit_trap.json`: on a no-edge market, DSR + PBO (0.91) flag
  naive best-of-N selection as luck, not skill, before capital is committed.
- **Tournaments on real Bitget data (1h)** — `bitget_btc_perp/`, `bitget_eth_perp/`,
  `bitget_sol_perp/`, `bitget_tokenized_aapl/` (Track 3): leaderboards + signed
  hash-chained ledgers + trade CSVs (timestamp/pair/side/price/qty/balance Δ).
- **External integration** — a `FirewallClient` SDK (`bitarena/client.py`) +
  `scripts/integrate_example.py`: a third-party bot vets every trade and **offline-verifies**
  each signed verdict in a few lines, runnable against the live deploy; plus
  `external_agent_session.json`, a recorded session. Track-2 "another developer integrated it".
- **Funding-carry edge study** — `funding_carry.json`: real Bitget funding history,
  walk-forward + Deflated Sharpe.
- **Live LLM debate** — `llm_debate.json`: a real Qwen analyst debate, firewall-gated.
- **Capital allocator** — `allocator.json`: trust-weighted vs equal-weight.

## Security rigor (Track 2 depth)

See `THREAT_MODEL.md` — a real threat model for the firewall: 15 enumerated threats, each
mapped to the gate/mechanism that stops it and the test or red-team case that proves it, plus
the residual risks it does *not* cover (host/key compromise, oracle trust). For a safety-firewall
project this is the artifact that separates "some gates" from a threat-modeled system.

## Honesty note (judges reward this)

See `SELF_ASSESSMENT.md` — a rubric-by-rubric rating with real limits stated, not hidden
(no price-directional agent reliably beats buy-hold on flat data; the swarm's chop edge is
directional but not statistically significant; the Agent Hub skills use honest offline
fallbacks). Honest self-assessment is an explicit scoring criterion.

---

## Owner action checklist (the only things left, all yours)

> Pre-push safety: audited — **no API keys in any git-tracked file** (Playbook and Qwen
> keys never committed; `.env` is gitignored and untracked). Safe to make the repo public.

1. ✅ **DONE — pushed to https://github.com/Pratiikpy/agent-arena** (public,
   CI green, **v0.1.0** released, 10 topics set). Secrets audited: `.env`/`.keys`/`*.pem`
   excluded, no Playbook/Qwen keys in any tracked file. Push updates with
   `git add -A && git commit -m "..." && git push` from `.research/bitarena`.
2. ✅ **DONE — live at https://bitarena.vercel.app** (UI + signed firewall + `/verify`,
   deployed to Vercel under your account). The headline (firewall / verify / leaderboard /
   UI) is stateless and runs serverless; for the continuously-running *stateful* arena
   (`/live`), a container host (`render.yaml` / `DEPLOY.md`) is the path. *To re-deploy:
   `vercel --prod` from `.research/bitarena` (already linked to the `bitarena` project).*
3. **[YOU]** Record the ≤3-min demo video (`DEMO.md`) and paste the link.
4. **[YOU]** Post the #BitgetHackathon quote-tweet; paste the link.
5. **[YOU]** Submit with your registration UID, primary track = Trading Infra. **First verify
   which of the two form URLs is live** (see the DQ-CRITICAL note at the top) — wrong form = not
   submitted = disqualified.
6. *(Optional, highest-leverage)* move from "paper" to "live trading" with one real
   dust-sized Bitget order — **the tooling is ready**: add trade-permission keys to `.env`
   (a dedicated sub-account), then `uv run python scripts/place_live_order.py --confirm`.
   It's dry-run by default, places only the size the **firewall ALLOWs**, and writes the
   signed `evidence/live_order_receipt.json` (the verifiable live-trading record).

Everything else — code, tests, evidence, the published Playbooks, docs — is done.

## Ready-to-paste assets (for the owner actions)

**GitHub repo description (one-liner):**
> Agent Arena — the trust layer for autonomous trading agents on Bitget: a signed,
> verifiable safety firewall + overfit-aware tournament + a live, self-improving arena.
> 4 published GetAgent Playbooks.

**GitHub topics:** `bitget` `trading-agents` `ai-agents` `crypto` `algorithmic-trading`
`reinforcement-learning` `mcp` `fastapi` `python` `hackathon`

**Community post / #BitgetHackathon (quote the [Bitget tweet](https://x.com/Bitget_AI/status/2062506424085917944), tag @Bitget_AI).**
Each tweet below is ≤280 chars — post the first as the quote-tweet, the rest as a thread:

> **1/** AI trading agents are here — but who stops one from blowing up?
>
> I built **Agent Arena** for #BitgetHackathon @Bitget_AI: a signed safety firewall every
> agent order must pass, + overfit-aware scoring that funds skill, not luck.
>
> Live, verify it yourself 👇 https://bitarena.vercel.app

> **2/** Don't trust me — **click the live verdict** on the page: it verifies the Ed25519
> signature **in your browser**. Flip one byte → watch it break. Tamper-evident, no server, on
> live data. 24-case red-team: **0 unsafe**. ~0.1 ms/verdict — gating every trade is ~free.

> **3/** Agents are ranked by Deflated Sharpe / PBO — not raw PnL — so a lucky backtest gets
> exposed, not crowned. 4 strategies already published on Bitget GetAgent. The arena runs on
> real Bitget data.

> **4/** Open source (MIT, 265 tests, CI-green): https://github.com/Pratiikpy/agent-arena —
> deploy it, integrate over MCP/HTTP in minutes, or verify any certificate offline. The trust
> layer for agentic trading. #BitgetHackathon @Bitget_AI
