# Agent Hub Skill briefs

The arena's five Agent Hub perception channels (macro · sentiment · news · on-chain ·
technical) consume a JSON **brief** from this directory — the shape a live Bitget Agent Hub
Skill produces. Drop a brief here (or point `$BITARENA_BRIEFS_DIR` elsewhere) and that channel
switches from its tagged offline `(fallback)` to the live skill **automatically — no code change**.

## Format

One file per skill, optionally per symbol. The loader checks, in order,
`<skill>_<SYMBOL>.json` then `<skill>.json`:

```json
{ "score": -0.4, "confidence": 0.8, "summary": "fear elevated; funding negative" }
```

- `score` — the skill's directional read in `[-1, +1]` (clamped).
- `confidence` — `[0, 1]` (clamped; default `0.6`).
- `summary` — short rationale, shown in the signal detail.

## Wiring a real Bitget Skill

Two ways to obtain a real Skill brief, both ending in a JSON file dropped here:

- **On-platform:** run the Skill on Bitget GetAgent and export its result.
- **Programmatic:** call the Skill Hub via Bitget's `agent_hub` MCP server
  (`github.com/BitgetLimited/agent_hub` — `npx bitget-hub` / `bitget-mcp-server`, with your
  Agent Hub key) and write its output into the format above.

Then:

1. Save it as `<skill>_<SYMBOL>.json` (e.g. `sentiment_BTCUSDT.json`) in this folder.
2. The next arena/debate run uses it as a live signal (`source: agent_hub:sentiment`, with no
   `(fallback)` tag) — no code change.

No brief present → the channel falls back to a deterministic price-action proxy, **clearly
tagged `(fallback)`** so nothing offline is ever presented as a live skill call.
