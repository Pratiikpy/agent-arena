# config/

**`issuer_pubkey.hex`** — Agent Arena's canonical Ed25519 **public** issuer key
(`c2f8243b…`, issuer fingerprint `98683e5cbe6313a0`). It is the trust anchor for the
"don't trust us, verify it yourself" flow:

- A certificate's signature proves **integrity** (it wasn't tampered with) against the
  key embedded in the cert.
- To prove **authenticity** (it was actually signed by Agent Arena, not a forger who
  self-signed with their own keypair), pin the cert's `public_key_hex` against this file:

  ```bash
  uv run python scripts/verify_cert.py --file cert.json --issuer-key config/issuer_pubkey.hex
  # -> signature VALID + trusted issuer
  ```

  The live deploy's `GET /pubkey` returns the same key, and `POST /verify` reports
  `valid` (integrity) and `trusted_issuer` (authenticity) separately.

This is a **public** key — safe to commit. The matching private key is never committed
(`.keys/` and `*.pem` are gitignored); the deployment injects it via the
`ARENA_SIGNING_KEY_B64` secret so the live issuer matches this published key.
