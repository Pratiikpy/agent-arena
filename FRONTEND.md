# Agent Arena — Frontend Handoff Spec

> For the designer / frontend engineer. This document is self-contained: it has the
> product story, the design direction, every screen, the full API contract, and **real
> sample data** pulled from the running backend. You should not need to read the Python
> to design or build the UI.
>
> The backend already serves everything below. This spec was the basis for the
> production UI now shipped in `web/index.html`; it remains the reference contract
> (screens, API shapes, formatting). A `Verify` screen for `POST /verify` was added on
> top of the page map below.

---

## 1. What this product is (the soul)

**Agent Arena is the trust layer for autonomous trading agents on Bitget.**

Two ideas, and the whole UI should make both *felt*:

1. **A safety firewall.** Every trade any agent wants to make is checked by a gate that
   returns a cryptographically **signed verdict** — `ALLOW`, `ALLOW_CAPPED`, or
   `REJECT` — before anything hits the exchange. Nothing can bypass it.
2. **An honest scoreboard.** Multiple AI agents compete on real Bitget data, and they're
   ranked with anti-overfitting math (not just "who made money"), so luck is exposed.

Emotional target: **"instrument-grade trust."** It should feel like a cross between a
professional trading terminal and a security/audit console — precise, calm, verifiable.
Not playful, not hype. Numbers are first-class citizens.

Audience: hackathon judges first (they'll click around for 2–3 minutes), then developers.

---

## 2. Visual direction (suggestion — you own the final aesthetic)

- **Mode:** dark-first. Near-black background (`#0b0e14`-ish), elevated panels a notch
  lighter. A light mode is nice-to-have, not required.
- **Type:** a clean grotesk for prose (Inter/Geist), a **monospace for all numbers,
  hashes, and verdicts** (JetBrains Mono / Geist Mono). Monospace is the signature.
- **Accent + status colors are semantic and must be consistent everywhere:**
  - `ALLOW` → green/teal (trust)
  - `ALLOW_CAPPED` → amber (allowed but constrained)
  - `REJECT` → red
  - `verified / signed` → a teal "trust" accent with a lock/check glyph
  - positive PnL → green, negative → red (muted, not neon)
- **Density:** data-dense but breathable. Tables and cards, not big marketing whitespace
  — except the landing hero.
- **Motion:** restrained. A verdict "stamping" in, an equity line drawing, a hash
  copy-confirm. No bouncing. Respect `prefers-reduced-motion`.
- **Signature moment:** the **signed certificate block** — render it like a stamped,
  tamper-proof seal (mono hashes, a green "✓ signature valid" badge). This is the image
  people should remember.

---

## 3. Page map

```
/                 Landing / hero  ........... the pitch + a live firewall try-it
/firewall         Firewall console .......... interactive: submit an intent → signed verdict
/arena            Leaderboard ............... the tournament: agents ranked, equity curves
/arena/:agentId   Agent detail .............. one agent's curve, trades, metrics
/debate           LLM debate view ........... the Qwen bull/bear/risk transcript + gate
/ledger           Signed trade log .......... tamper-evident records, Bitget-required fields
/verify           Independent verifier ...... paste any certificate → offline ✓/✗ signature check
```
A single-page dashboard with sections is equally fine — the content groupings matter more
than the routing.

---

## 4. Screens

For each screen: **purpose · data it shows · components · states · backing endpoint.**

### 4.1 Landing / hero  (`/`)
- **Purpose:** in 5 seconds, say what it is; in 15, let them try the firewall live.
- **Shows:** headline ("The trust layer for autonomous trading agents on Bitget"),
  one-line subhead, three proof chips (`signed firewall`, `live Bitget data`,
  `overfit-aware scoring`), and an inline **mini firewall try-it** (symbol + side +
  notional → verdict pill + "✓ signature valid").
- **Components:** Hero, ProofChips, MiniFirewallWidget, primary CTAs → `/arena`, `/firewall`.
- **States:** the try-it has idle / submitting / result / error.
- **Endpoint:** `POST /firewall`, plus `GET /health` for an "online" dot.

### 4.2 Firewall console  (`/firewall`)  — the killer demo
- **Purpose:** let anyone push a trade through the gate and see a signed verdict. This is
  the "curl in 10 seconds" moment, made visual.
- **Shows (input):** `symbol`, `side` (buy/sell), `instrument` (spot/perp/tokenized_equity),
  `notional_usd` **or** `quantity`, optional `equity_usd`, `current_exposure_usd`.
- **Shows (output):**
  - a big **verdict pill** (ALLOW / ALLOW_CAPPED / REJECT, color-coded) + the `reason`
  - `effective_notional_usd` (and, when capped, the "from $X → $Y" framing)
  - a **gates checklist** — each gate name with a pass/fail tick (`halt`, `expiry`,
    `universe`, `instrument`, `quote`, `min_price`, `daily_count`, `leverage`,
    `max_order_notional`, `max_total_exposure`, `max_leverage_exposure`)
  - the **Certificate block** (§4.3)
- **Presets:** buttons that pre-fill interesting cases: "tiny order → ALLOW",
  "huge order → CAPPED", "exposure full → REJECT". (Designers: these make the demo sing.)
- **States:** idle / submitting / verdict / validation-error (e.g., neither notional nor
  quantity → 400).
- **Endpoint:** `POST /firewall`.

### 4.3 Certificate block (component, used on 4.1/4.2/4.7)
- **Purpose:** make "signed and verifiable" tangible.
- **Shows:** `decision`, `effective_notional_usd`, `issued_at`, `issuer` (short
  fingerprint, mono), `nonce`, `intent_hash` (mono, truncate middle:
  `779b7c30…2ae9348`), `signature_hex` (mono, truncated, copyable), `public_key_hex`
  (mono, copyable), and a prominent **`✓ signature valid`** badge driven by
  `certificate_valid`.
- **Nice touch:** a "tamper" toggle that flips one field client-side and shows the badge
  turn red — mirrors `firewall_demos.json → tamper_detection`. Optional but powerful.

### 4.4 Arena leaderboard  (`/arena`)
- **Purpose:** the tournament. Rank the agents honestly.
- **Header strip:** `symbol`, `instrument`, `source` (e.g. `bitget:1m:1000bars`), `ticks`,
  `starting_cash`, `issuer`, and two trust badges: **`ledger ✓ verified`** and a
  **PBO gauge** (`overfitting.pbo`) with a plain-language label (see §9).
- **Table (one row per agent), columns:** `rank`, `agent_id`, `final_equity`,
  `total_return` (%), `sharpe`, `sortino`, `max_drawdown` (%), `win_rate` (%), `trades`,
  `fees_usd`, `psr`. Rank 1 highlighted. Color PnL.
- **Firewall summary card:** from `firewall.totals` — `intents`, `allow`, `allow_capped`,
  `reject`. A small stacked bar reads great here.
- **Per-agent firewall detail:** expand a row to show `firewall.by_agent[id]` incl.
  `reject_reasons`.
- **Empty state:** if the endpoint 404s → "No tournament run yet" with the command to run one.
- **Endpoint:** `GET /leaderboard`.

### 4.5 Agent detail  (`/arena/:agentId`)
- **Purpose:** one agent in depth.
- **Shows:** its leaderboard row metrics as stat cards; an **equity curve** (derived from
  its ledger balances over time — `account_balance_usd` vs `timestamp_ms`); its recent
  signed trades (§4.7 table, filtered to this agent).
- **Endpoint:** `GET /leaderboard` (metrics) + `GET /ledger?agent=:agentId` (trades/curve).

### 4.6 LLM debate view  (`/debate`)
- **Purpose:** show that a real LLM agent reasons — and is still gated.
- **Shows:** `symbol`, `source`, a `qwen_available` badge, `decision_source`
  (`qwen` / `deterministic`), the **rationale** quote (hero it — e.g. *"Oversold RSI
  favors bounce, but weak trend and analyst disagreement limit conviction."*), the
  **9 signals** as a row of gauges grouped by source (4 `technical`, 5
  `agent_hub:*`), `net_signal` and `agreement` as two dials, then the resulting
  `intent` and its firewall `verdict` (incl. HOLD when no order).
- **Signals visual:** each signal is a name + a -1…+1 bar (green right / red left) +
  confidence as opacity/height. Make the *disagreement* visible — that's the thesis.
- **Endpoint:** `GET /debate` (live) — serves the debate JSON shape below (falls back to
  `evidence/llm_debate.json`).

### 4.7 Signed ledger / trade log  (`/ledger`)
- **Purpose:** the verifiable audit trail (and the exact fields Bitget requires).
- **Shows:** an agent selector; a table with the **Bitget-required fields**:
  `timestamp_ms` (render as UTC time), `pair`, `direction`, `price`, `quantity`,
  `notional_usd`, `fee_usd`, `balance_change_usd`, `account_balance_usd`, `decision`.
  Plus a small "chain" affordance: each row links to the next via `prev_hash` →
  `record_hash`; show a **`chain ✓`** badge for the whole ledger.
- **Detail drawer (per row):** the full signed record incl. `cert_hash`, `prev_hash`,
  `record_hash`, `signature_hex`, `public_key_hex` (all mono, copyable).
- **Empty/404:** "No ledger for agent X."
- **Endpoint:** `GET /ledger?agent=swarm&limit=50`.

### 4.8 Trust / overfitting explainer (small reusable panel)
- **Purpose:** teach `PBO` and `PSR`/Deflated Sharpe in one sentence each, with the live
  number. Use on `/arena`. Copy in §10.

---

## 5. API contract

Base URL (local dev): `http://localhost:8000`. All JSON. No auth. CORS: ask backend to
enable for your dev origin.

### `GET /health`
Response:
```json
{ "status": "ok", "issuer": "98683e5cbe6313a0", "version": "0.1.0" }
```

### `POST /firewall`
Request body (one of `notional_usd` / `quantity` required):
```json
{
  "agent_id": "external-agent",
  "symbol": "BTCUSDT",
  "side": "buy",
  "instrument": "spot",
  "notional_usd": 50,
  "quantity": null,
  "leverage": 1.0,
  "equity_usd": 10000,
  "current_exposure_usd": 0
}
```
`side`: `"buy"|"sell"`. `instrument`: `"spot"|"perp"|"tokenized_equity"`.
Response (real ALLOW example):
```json
{
  "decision": "ALLOW",
  "reason": "within all limits",
  "effective_notional_usd": 50.0,
  "gates": [
    {"gate": "halt", "passed": true, "detail": ""},
    {"gate": "universe", "passed": true, "detail": ""},
    {"gate": "instrument", "passed": true, "detail": ""},
    {"gate": "quote", "passed": true, "detail": ""},
    {"gate": "daily_count", "passed": true, "detail": "", "limit": 200, "attempted": 0},
    {"gate": "max_order_notional", "passed": true, "limit": 2000.0, "attempted": 50.0}
  ],
  "certificate": {
    "version": 1,
    "intent_hash": "779b7c303be232bf3d89f10f7824665221120f9dc6da6df193abfac4f2ae9348",
    "decision": "ALLOW",
    "effective_notional_usd": 50.0,
    "issued_at": "2026-06-19T04:38:57.712860+00:00",
    "issuer": "98683e5cbe6313a0",
    "nonce": "9f2gamRXlP3_MRf4",
    "signature_hex": "53ce389f8657b8b3...271bb005",
    "public_key_hex": "c2f8243b0d573587f285c830a868acd19249d17d59ecbf9329e796dfed6fb630"
  },
  "certificate_valid": true
}
```
- **ALLOW_CAPPED:** `decision: "ALLOW_CAPPED"`, `reason: "capped from $999,999.00 to $2,000.00"`, `effective_notional_usd: 2000.0`.
- **REJECT:** `decision: "REJECT"`, `reason: "no headroom under sizing caps"`, `effective_notional_usd: null`, `certificate` still present and signed.
- **400:** invalid intent (e.g., neither `notional_usd` nor `quantity`) → `{ "detail": "<reason>" }`.

### `GET /leaderboard`
Returns the most recent tournament. Real shape (BTC perp, 1000 ticks) — abbreviated; see
`evidence/bitget_btc_perp/leaderboard.json` for the full file:
```json
{
  "symbol": "BTCUSDT", "instrument": "perp", "ticks": 1000,
  "starting_cash": 10000.0, "issuer": "98683e5cbe6313a0",
  "source": "bitget:1m:1000bars",
  "leaderboard": [
    {"agent_id": "baseline-momentum", "rank": 1, "final_equity": 10090.61,
     "total_return": 0.009061, "sharpe": 0.031001, "sortino": 0.029601,
     "max_drawdown": -0.006913, "win_rate": 0.453, "trades": 3,
     "fees_usd": 3.03, "psr": 0.8363, "profit_factor": 1.099, "calmar": 1.31, "periods": 1000}
    /* …one object per agent, already sorted by rank… */
  ],
  "firewall": {
    "totals": {"intents": 551, "allow": 389, "allow_capped": 162, "reject": 0, "exec_fail": 0},
    "by_agent": {"swarm": {"intents": 79, "allow": 79, "allow_capped": 0, "reject": 0, "reject_reasons": {}}}
  },
  "overfitting": {"pbo": 0.0, "insufficient": false, "n_combinations": 252},
  "ledger_verified": true,
  "ledger_entries": {"swarm": 373, "persona-team": 258, "rl-qlearn": 208}
}
```
404 when no run exists: `{ "detail": "no tournament run yet" }`.

### `GET /ledger?agent=swarm&limit=50`
```json
{
  "agent": "swarm",
  "count": 373,
  "records": [
    {
      "seq": 0, "ts": 1781784600000, "agent_id": "swarm", "symbol": "BTCUSDT",
      "side": "sell", "price": 63975.11, "quantity": 0.01021873,
      "notional_usd": 653.74, "fee_usd": 0.39,
      "balance_before_usd": 10000.0, "balance_after_usd": 9999.46,
      "decision": "ALLOW", "cert_hash": "94ddff9c…f75db5",
      "prev_hash": "0000…0000", "record_hash": "69f48879…6d8b02",
      "signature_hex": "b27c04b5…a888204",
      "public_key_hex": "c2f8243b…d6fb630"
    }
  ]
}
```
404: `{ "detail": "no ledger for agent 'X'" }`.

### LLM debate data (`evidence/llm_debate.json`, or ask backend for `GET /debate`)
```json
{
  "symbol": "BTCUSDT", "instrument": "perp", "source": "bitget:120bars",
  "qwen_available": true, "decision_source": "qwen",
  "rationale": "Oversold RSI favors bounce, but weak trend and analyst disagreement limit conviction.",
  "signals": [
    {"name": "momentum", "source": "technical", "value": -0.079, "confidence": 0.997},
    {"name": "mean_reversion", "source": "technical", "value": 0.725, "confidence": 0.797},
    {"name": "sentiment", "source": "agent_hub:sentiment(fallback)", "value": 0.828, "confidence": 0.4}
    /* 9 signals total: 4 technical + 5 agent_hub:* */
  ],
  "net_signal": 0.211, "agreement": 0.73,
  "intent": null,
  "verdict": { "decision": "HOLD", "reason": "no conviction -> no order" }
}
```

---

## 6. Data dictionary (field → meaning, format)

| Field | Meaning | Display |
|---|---|---|
| `decision` | firewall ruling | pill: ALLOW=green, ALLOW_CAPPED=amber, REJECT=red, HOLD=grey |
| `effective_notional_usd` | size after capping (null on REJECT) | USD, 2dp; show "—" if null |
| `certificate_valid` | signature verifies | ✓ green badge / ✗ red |
| `issuer` | signing-key fingerprint | mono, as-is (16 hex) |
| `intent_hash`,`signature_hex`,`*_hash`,`public_key_hex` | crypto material | mono, truncate middle, copyable |
| `total_return` | period return | percent, 2dp, signed, colored |
| `sharpe`,`sortino`,`psr`,`calmar` | risk-adjusted stats | number, 2–3dp (per-period, not annualized) |
| `max_drawdown` | worst peak-to-trough | percent, 2dp, negative, red |
| `win_rate` | fraction of up-periods | percent, 1dp |
| `trades`,`periods`,`ticks`,`intents` | counts | integer with thousands sep |
| `fees_usd`,`final_equity`,`*_usd` | money | USD, 2dp, thousands sep |
| `overfitting.pbo` | prob. of backtest overfitting | 0–1 → percent + label (§9); null/insufficient → "n/a" |
| `firewall.totals.*` | gate tallies | integers; stacked bar |
| `ts`/`timestamp_ms` | epoch ms | render UTC `YYYY-MM-DD HH:mm:ss` |
| `side`/`direction` | buy/sell | arrow + label; buy green-ish, sell red-ish |
| `decision_source` | qwen / qwen-cached / deterministic | small tag |
| `agreement` | 1=unanimous, 0=split | dial 0–100% |
| `net_signal` | -1…+1 confidence-weighted | center-zero bar |

---

## 7. Component inventory
- `VerdictPill` (ALLOW / ALLOW_CAPPED / REJECT / HOLD)
- `CertificateBlock` (with `✓ signature valid`, copyable mono fields, optional tamper toggle)
- `GatesChecklist` (gate name + pass/fail + detail/limit)
- `LeaderboardTable` (sortable, rank-highlighted, colored PnL)
- `StatCard` (label + big number + sub)
- `EquityCurveChart` (line; from ledger balances)
- `FirewallSummaryBar` (stacked allow/capped/reject)
- `SignalGaugeRow` (-1…+1 bar with confidence)
- `PboGauge` / `TrustBadge` (pbo + ledger verified)
- `HashChip` (truncated mono + copy)
- `TradeLogTable` + `RecordDrawer`
- `OnlineDot` (from `/health`)
- `EmptyState`, `ErrorState`, `Skeleton` loaders

---

## 8. Number & status formatting (keep consistent)
- USD: `$10,090.61`. Large: `$10.1k` allowed in compact contexts; full value on hover.
- Percent: `+0.91%`, `-1.41%` (2dp, always signed for returns/PnL).
- Ratios (sharpe/psr): 2–3 significant decimals; these are **per-period, not annualized** —
  do not multiply or relabel them.
- Hashes/keys: monospace, truncate middle to `xxxxxxxx…xxxxxx`, full value copyable and on hover.
- Timestamps: epoch ms → UTC string; show relative ("3m ago") only as secondary.
- Decision colors are fixed (see §2) and used identically across pills, rows, and charts.

---

## 9. The PBO / trust label (plain language)
`overfitting.pbo` ∈ [0,1]. Lower is better.
- `< 0.1` → **"Robust"** (green) — the ranking is unlikely to be luck.
- `0.1–0.4` → **"Mixed"** (amber).
- `> 0.4` → **"Likely overfit"** (red) — the leader is probably luck, not skill.
- `insufficient: true` or `pbo: null` → **"Not enough data"** (grey).
Tooltip: "Probability of Backtest Overfitting — the chance that the in-sample best agent
is not actually the best out-of-sample." PSR tooltip: "Probability the agent's Sharpe is
truly above zero, adjusted for non-normal returns."

---

## 10. Copy bank
- Hero H1: **"The trust layer for autonomous trading agents."**
- Hero sub: "Every trade an AI agent makes passes a signed safety firewall. Every agent
  is scored for skill, not luck. Live on Bitget."
- Firewall empty: "Submit a trade to see a signed verdict."
- Leaderboard empty: "No tournament has run yet. Run `scripts/run_arena.py` to populate."
- Ledger empty: "No signed trades for this agent yet."
- Error (any fetch): "Backend unreachable — start the API with `uvicorn bitarena.api.app:app`."
- Cert badge: `✓ signature valid` / `✗ signature invalid (tampered)`.
- Capped note: "Requested $999,999 → capped to $2,000 by the mandate."

---

## 11. Responsive & accessibility
- Mobile: tables collapse to stacked cards; the firewall console stays usable (it's the
  demo). Hero stacks.
- Color is never the only signal — pair verdict colors with text/icons (color-blind safe).
- All hashes/keys have a copy button with an accessible label and a copied-confirmation.
- Respect `prefers-reduced-motion`. Charts need text alternatives (the stat cards suffice).
- Target WCAG AA contrast on the dark theme.

---

## 12. Handoff checklist
- [ ] Landing with live mini-firewall try-it
- [ ] Firewall console with presets + gates checklist + certificate block (+ tamper toggle)
- [ ] Leaderboard with header strip, table, firewall summary, PBO/verified badges
- [ ] Agent detail with equity curve + filtered trades
- [ ] LLM debate view (rationale hero + signal gauges + net/agreement + gated verdict)
- [ ] Signed ledger table + record drawer
- [ ] Consistent verdict/PnL colors, mono numbers, truncated copyable hashes
- [ ] Empty / loading / error states for every fetch
- [ ] `/health` online indicator

**Backend asks:** `GET /debate` and CORS are live. Remaining nice-to-have: an
SSE/websocket stream so the leaderboard updates tick-by-tick during a live run.
