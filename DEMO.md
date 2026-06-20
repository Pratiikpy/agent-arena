# Agent Arena — 3-minute demo storyboard

A tight script for the demo video (max 3 min). Every step is a real command whose
output is shown on screen. Times are cumulative.

**Live deploy:** the firewall, `/verify`, leaderboard, debate, and UI are deployed at
**https://bitarena.vercel.app** — you can run the firewall/verify beats against it (browser
or `curl`) instead of locally, to show it working as a public service.

## 0:00 – 0:25 · The hook
> "Everyone's building AI agents that place trades. Nobody's building the layer that
> decides which agents to trust — and stops any of them from blowing up. That's Agent
> Arena: a live safety firewall and proving ground for autonomous trading agents on
> Bitget."

Open **https://bitarena.vercel.app** and point at the **LIVE FIREWALL** badge ticking in the
corner — the real BTC price and a freshly Ed25519-signed verdict every few seconds, on the
public URL. "This is live right now." Then show the architecture diagram from the README.

## 0:25 – 1:05 · The firewall is real, signed, and verifiable by anyone
Run, on screen:
```bash
uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 50
uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 999999
```
First is `ALLOW` with an Ed25519-signed certificate; second is `ALLOW_CAPPED` (the
oversized order is clamped to the mandate). Then prove it can't be faked:
```bash
uv run python scripts/demo_firewall.py --symbol BTCUSDT --side buy --notional 50 > v.json
uv run python scripts/verify_cert.py --file v.json     # -> ✓ signature VALID (fully offline)
```
"Don't trust us — verify it yourself. And it's effectively free: ~0.1 ms per signed
verdict, ~9,700 a second on one core."

Or show it **live** on the deployed service (same signed verdict, public URL):
```bash
curl -s https://bitarena.vercel.app/firewall -H 'content-type: application/json' \
  -d '{"symbol":"BTCUSDT","side":"buy","notional_usd":999999}'   # -> signed ALLOW_CAPPED
```

## 1:05 – 1:40 · A real LLM agent, governed by the firewall
```bash
uv run python scripts/llm_debate.py --symbol BTCUSDT --instrument perp
```
Show the live Qwen output: the five Agent Hub signals, the debate rationale
(*"oversold RSI favors a bounce, but weak trend and analyst disagreement limit
conviction"*), and that the resulting intent still goes through the firewall for a
signed verdict. "Even a confident LLM cannot bypass the gate."

## 1:40 – 2:15 · The tournament + honest scoring
```bash
uv run python scripts/run_arena.py --source bitget --instrument perp --bars 1000
```
Show the leaderboard: seven autonomous agents trading real Bitget data (including the
funding-carry competitor that harvests real perpetual funding), the firewall
stats (allowed / capped), `ledger_verified=True`, and the cross-agent `PBO`. Say it
plainly: "On flat real data nobody reliably beats the benchmark — and the Arena reports
that. The PBO number tells you when the leader is luck, not skill." Then the regime
scenario (`make_evidence`): "In the chop, the conflict-gated swarm flattened — 51 trades,
−1.9% — while the naive momentum bot whipsawed at 108 trades and lost −4.9%. The thesis
holds exactly where it claims to."

## 2:15 – 2:45 · Shipped to Bitget's own platform
> "The Arena doesn't just run agents — it ships them."

Open Bitget → Playbook → Explore and show the **four published GetAgent Playbooks**
(Momentum Breakout BTC — Sharpe 1.68, PF 2.33; Momentum Breakout ETH — PF 1.42; Adaptive
Regime BTC — PF 1.74; Adaptive Regime ETH — Sharpe 2.15, PF 3.34), each with a real
on-platform backtest. Mention that three more strategies were backtested and *withheld* for
underperforming on real data — "we publish only when the evidence earns it." (Details in
`playbook/PUBLISHED.md`.)

## 2:45 – 3:00 · Infra + UI anyone can plug into
Open the **live deployed UI at https://bitarena.vercel.app** (the firewall console,
leaderboard, signed ledger, and the independent **Verify** tab — all served from the public
deploy; or `uvicorn bitarena.api.app:app` locally), a `curl` to `/firewall`, and the MCP
server (`vet_trade`, `get_leaderboard`) callable from Claude/Cursor. Then show a third party
integrating in seconds — `uv run python scripts/integrate_example.py` runs a bot that vets and
**offline-verifies** every trade against the live deploy (ALLOW / CAPPED / REJECT). Then the
**paper → live** beat: `make live` advances the arena on real Bitget data each run —
persisting signed ledgers, funding, and even the agents' learning — served at `/live`, with
the **LIVE FIREWALL** heartbeat badge ticking the live price + a fresh signed verdict. Close:
> "Agent Arena is the trust layer for agentic trading: a signed firewall no agent can
> bypass, overfit-aware scoring that tells you which agents deserve capital, three
> strategies already live on Bitget, and an arena that runs live on a schedule. It runs
> on real Bitget data, today."

## Capture checklist
- Terminal with a dark theme, large font.
- Pre-warm `uv` (run once before recording so installs don't show).
- Have `.env` populated with the Bitget Qwen key so the LLM step is live.
- For the UI beat: `make serve`, then open `http://localhost:8000` and click the Verify tab.
- For the live beat: run `make live` once or twice beforehand so `/live` shows a populated
  ● LIVE leaderboard on the Arena tab.
- Keep each command's output on screen long enough to read the key line.
