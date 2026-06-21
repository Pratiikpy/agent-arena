# Threat Model — the Agent Arena firewall

A safety firewall is only as good as the threats it actually stops. This document states
what the firewall defends against, the mechanism that stops each threat, and the
**test or red-team case that proves it** — plus the residual risks it does *not* cover.
Honesty about the boundary is part of the design.

## Scope and boundary

**What it defends:** the firewall is the single execution chokepoint every order from every
agent passes through. It returns a fail-closed, Ed25519-signed `ALLOW` / `ALLOW_CAPPED` /
`REJECT` certificate **before** anything reaches the exchange. Its job is to bound what an
agent's *decisions* can do, no matter how the agent was built (rule-based, RL, or an LLM that
hallucinates).

**What it does not defend:** it is **not** an OS-level sandbox. It bounds order *decisions*,
not arbitrary code execution on the host, and it assumes the signing key and the host are not
compromised (see *Residual risks*). That boundary is the threat model, stated plainly.

## Trust assumptions

1. **The issuer signing key is secret.** Anyone with it can mint valid certificates. Custody
   is the operator's responsibility (a dedicated key, never committed — `.env` is gitignored).
2. **The published issuer public key is authentic.** Verifiers pin it
   (`config/issuer_pubkey.hex`); a valid signature from any *other* key is rejected as the
   wrong issuer (authenticity, not just integrity).
3. **The exchange quote feed is the price oracle.** The firewall checks the quote's freshness
   and sanity, but trusts the venue itself for the price.

## Threat actors

- A **buggy** agent (an off-by-one or a runaway loop sizing 100× too large).
- A **rogue / compromised** agent (actively trying to breach the mandate).
- A **hallucinating LLM** agent (confidently proposing a catastrophic order).
- A **forger** downstream of the agent, trying to fake or tamper with a verdict.

## Threats → mitigations → proof

Every order is evaluated fail-closed: a gate that cannot positively confirm safety (including
on missing data or an internal error) returns `REJECT` or caps the size. Gates run in order
(`firewall.evaluate`), and the order's size is then capped to the order- and exposure-notional
limits (`ALLOW_CAPPED`).

| # | Threat | Vector | Mitigation | Proof |
|---|--------|--------|------------|-------|
| 1 | Drain the account with one huge order | agent requests an enormous notional | order-notional cap → `ALLOW_CAPPED` to the mandate size | `redteam` *sizing*; `test_firewall`; `firewall_value.json` ($8,574 saved) |
| 2 | Stack exposure past the mandate | many orders accumulate total exposure | exposure cap (reduction-aware) → cap/reject | `redteam` *exposure*; `test_firewall` reduce-only; firewall **monotonicity** property |
| 3 | Trade a forbidden / unknown symbol | order on an excluded or off-universe symbol | `gate_universe` | `redteam` *universe*; `test_firewall_properties` excluded-symbol fuzz |
| 4 | Trade the wrong instrument | spot order under a perp-only mandate (or vice versa) | `gate_instrument` | `redteam` *instrument* |
| 5 | Trade while the arena is halted | order after a manual/operational halt | `gate_halt` | `redteam` *halt*; property INV3 (halted ⇒ reject) |
| 6 | Trade on an expired mandate | order after the mandate's expiry | `gate_expiry` | `redteam` *expiry* |
| 7 | Act on a stale or manipulated price | a stale or missing quote (feed outage / manipulation) | `gate_quote_sanity` — **fail-closed**, rejects with no clock or a too-old quote | `redteam` *quote*; `test_api` stale-quote |
| 8 | Sub-minimum / dust precision noise | order below the tradable minimum | `gate_min_price` / min-notional floor | `gate_min_price` unit coverage |
| 9 | Over-leverage | request leverage beyond the mandate ceiling | `gate_leverage_request` | `redteam` *leverage* |
| 10 | Order-rate abuse (spam / churn) | excessive orders per window | `gate_daily_count` | `redteam` *rate* |
| 11 | Whole-fleet blowup in a crash | every agent keeps buying into a fast drawdown | `gate_market_regime` — market-wide **kill-switch**: `FAST_RISK_OFF` permits de-risking only | `redteam` *regime*; `test_killswitch` (gate **and** end-to-end through the engine); `regime_killswitch.json` ($3,120 avoided) |
| 12 | Forge an `ALLOW` certificate | fabricate a verdict the firewall never issued | Ed25519 signature over canonical bytes | `test_signing` forgery; `verify_certificate` |
| 13 | Tamper with a signed verdict | mutate any field of a real certificate | signature verification fails on any change | `firewall_demos.json` tamper proof; in-browser Web-Crypto verify |
| 14 | Pass off a wrong-issuer certificate | a technically-valid signature from another key | issuer **pinning** to the published key | `test_signing` pinning; `verify_evidence` (all artifacts pinned) |
| 15 | Hide or rewrite a bad trade after the fact | edit / reorder / delete ledger records | append-only **hash-chained**, signed ledger | `test_ledger_properties` (mutation, reorder, mid-chain deletion, truncation all detected) |
| 16 | Trade a stale off-hours tokenized-stock "ghost price" | order on a tokenized US stock while the *underlying* US market is closed (the rToken can dislocate / gap at re-open) | session gate — tightens the off-hours order cap for tokenized equities (graduated containment, fail-safe), DST-aware | `redteam` *session* (off-hours gross oversize contained to the tightened cap); `test_session` (gate + DST boundaries); `tokenized_session_risk.json` (off-hours risk quantified) |

The aggregate guarantee is measured, not asserted: the red-team battery runs **22 attacks + 3
controls and lets through 0 unsafe orders**, every verdict signed (`redteam.json`).

## Design principles

- **Fail-closed.** The default is deny. A gate that can't confirm safety — including on an
  exception or missing input (no clock, no quote, malformed mandate) — denies or caps.
- **One chokepoint.** There is no ungated path exposed to an agent: the HTTP `/firewall`, the
  MCP `vet_trade`, and the arena's internal execution all route through the same `evaluate()`.
- **Verifiable, not trusted.** Every decision is signed and independently checkable — offline
  (`verify_evidence.py`), over HTTP (`/verify`), or **in a browser** with no server.
- **Tested adversarially.** Each gate has a red-team case and unit/property tests; safety
  invariants (never-exceeds-cap, monotonicity, excluded-symbol, non-finite, halt-rejects) are
  property-tested over thousands of random inputs.

## Operational security (audited)

A trust layer is only trustworthy if its own surface is. Audited and clean:

- **Secrets never committed.** The signing key, Bitget API keys, and the model key live only in
  `.env` (gitignored) or deploy env vars; the repo tracks only `.env.example` (placeholders). No
  key material is hardcoded, and the signing key is never logged — it only signs verdicts server-side.
- **Inputs are validated.** Every HTTP / MCP input is Pydantic-typed (bounded notional, enum
  side/instrument); the certificate verifier rebuilds through the model before checking. The one
  user-fed file parameter (`/ledger?agent=`) is regex-guarded against path traversal (CWE-22), and
  every other file-serving endpoint reads a fixed path, never user input.
- **The public API exposes no credentials.** `/firewall` and `/verify` are intentionally open (a
  firewall is a public good) but hold nothing to steal — they return signed *public* verdicts; the
  private key never leaves the server.

## Residual risks (honest)

- **Host / key compromise is out of scope.** With the signing key, an attacker mints valid
  certificates; with host code-execution, they bypass the process entirely. The firewall bounds
  *decisions*, not a compromised machine. Mitigation is operational: dedicated key, least
  privilege, a sub-account for live trading.
- **Oracle trust.** The firewall validates quote freshness/sanity but trusts the venue for the
  price itself; a venue printing a bad-but-fresh price is not detectable here.
- **Architectural, not kernel-enforced.** "No agent can bypass" is guaranteed by the single
  code path, not an OS sandbox — appropriate to the threat (an agent's order decisions), and
  stated as such rather than overclaimed.
