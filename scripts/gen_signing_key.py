"""Generate an Ed25519 signing key and print it base64-encoded for deployment.

    uv run python scripts/gen_signing_key.py

Set the printed value as the secret env var ARENA_SIGNING_KEY_B64 on your host so the
deployed firewall has a stable issuer across restarts. Keep it secret — anyone with it
can sign certificates as your arena.
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bitarena.firewall.signing import Signer


def main() -> None:
    sk = Ed25519PrivateKey.generate()
    pem = sk.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    b64 = base64.b64encode(pem).decode()
    fingerprint = Signer(sk).fingerprint
    print(f"# issuer fingerprint (public): {fingerprint}")
    print("# set this as a SECRET env var (do not commit):")
    print(f"ARENA_SIGNING_KEY_B64={b64}")


if __name__ == "__main__":
    main()
