# Deploy the Agent Arena firewall to a public URL

The firewall API is a small, stateless FastAPI app — it deploys to **Vercel (serverless)** or
any container host in minutes. Once live, anyone (a judge, an external agent) can `curl` a
**signed verdict** with no clone and no setup. That single fact is the strongest credibility
signal we have. The shipped live instance is **https://bitarena.vercel.app**.

## One-time: make a stable signing key
So the deployed firewall keeps the same issuer across restarts, generate a key and set it
as a **secret** env var (never commit it):
```bash
uv run python scripts/gen_signing_key.py
# copy the printed ARENA_SIGNING_KEY_B64=... value into your host's secrets
```
If you skip this, the firewall still works — it just generates a fresh key on each boot
(certs remain verifiable because the public key is embedded in every certificate).

## Option A — Vercel (this is how the live deployment runs)
The serverless surface (firewall / verify / pubkey / leaderboard / debate / ledger / **pulse**
+ the UI) runs on Vercel's Python runtime. `vercel.json` builds `api/index.py` (the FastAPI
entry) with `includeFiles: "**"` so the evidence pack is bundled; `api/requirements.txt` pins
the serverless deps.
```bash
npm i -g vercel
vercel env add ARENA_SIGNING_KEY_B64 production   # paste the stable b64 key -> consistent issuer
vercel --prod                                     # deploys from vercel.json
```
`/pulse` fetches live Bitget data on each call (the badge ticks a fresh signed verdict). The
continuously-*stateful* arena (`/live`) needs a scheduler — ship a committed snapshot, or use a
container host (below) running `live_step.py` on a cron.

## Option B — Render (easiest container, free tier)
1. Push this repo to GitHub.
2. Render → **New → Blueprint** → select the repo (`render.yaml` is detected).
3. Set the secret `ARENA_SIGNING_KEY_B64` (and optionally `BITGET_QWEN_API_KEY`).
4. Deploy. Health check is `/health`. Your URL: `https://agent-arena.onrender.com`.

## Option C — Fly.io
```bash
fly launch --no-deploy            # uses the Dockerfile
fly secrets set ARENA_SIGNING_KEY_B64=...  BITGET_QWEN_API_KEY=...
fly deploy
```

## Option D — Railway / any container host
Point it at the `Dockerfile`. Set `ARENA_SIGNING_KEY_B64` (and `BITGET_QWEN_API_KEY`)
as env vars. The container honors `$PORT`.

## Option E — local (no deploy)
```bash
uv run uvicorn bitarena.api.app:app --host 0.0.0.0 --port 8000
```

## Live mode (a continuously-growing tournament)
The arena can run **live**, not just as a backtest. Schedule `live_step.py` (cron, or a
deployed worker — hourly for 1h candles); each run fetches the latest Bitget candles +
funding, advances the arena, and persists state (portfolios + signed ledgers + cursor) so
it resumes across runs. `GET /live` then serves the growing tournament.
```bash
# e.g. crontab: every hour
0 * * * * cd /app && uv run python scripts/live_step.py --symbol BTCUSDT --instrument perp --state evidence/live
```

## Verify the live deployment
```bash
curl -s https://YOUR-URL/health
curl -s https://YOUR-URL/firewall -H 'content-type: application/json' \
  -d '{"agent_id":"judge","symbol":"BTCUSDT","side":"buy","notional_usd":999999}'
# -> ALLOW_CAPPED, with a signed certificate you can verify offline
```

Endpoints: `GET /health`, `POST /firewall`, `POST /verify` (independently check any
certificate), `GET /pubkey`, `GET /leaderboard`, `GET /live`, `GET /ledger?agent=...`,
`GET /debate`, and the **production UI served at `/`**.

The Docker image **bundles `evidence/last_run`** (the real signed leaderboard, the six
per-agent ledgers, and the LLM debate), so `/leaderboard`, `/ledger`, and `/debate` are
populated out of the box — no commit or mount step needed. To refresh them before a
build, re-run `uv run python scripts/run_arena.py` (it writes `evidence/last_run`).
