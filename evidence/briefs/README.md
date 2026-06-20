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

1. Run the Agent Hub Skill on Bitget (macro / sentiment / news / on-chain / technical).
2. Export its result into the format above, e.g. `sentiment_BTCUSDT.json`, in this folder.
3. The next arena/debate run uses it as a live signal (`source: agent_hub:sentiment`, with no
   `(fallback)` tag).

No brief present → the channel falls back to a deterministic price-action proxy, **clearly
tagged `(fallback)`** so nothing offline is ever presented as a live skill call.
