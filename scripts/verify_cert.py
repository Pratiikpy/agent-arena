"""Independently verify an Agent Arena certificate — fully offline, no server.

A certificate embeds its own Ed25519 public key and signature, so anyone can
verify it with nothing but this script. This is the "don't trust us, verify it
yourself" tool.

    # from a file
    uv run python scripts/verify_cert.py --file cert.json
    # or pipe a verdict/certificate JSON in
    cat verdict.json | uv run python scripts/verify_cert.py

Accepts either a bare certificate object or a full firewall verdict (it will pull
the `certificate` field out).
"""

from __future__ import annotations

import argparse
import json
import sys

from bitarena.domain import Certificate
from bitarena.firewall import verify_certificate

# Make output encoding-independent: on a default Windows console (cp1252) the ✓/✗ marks
# printed below would otherwise raise UnicodeEncodeError.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover - unusual stdio objects without reconfigure
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an Agent Arena certificate offline.")
    parser.add_argument("--file", help="path to a JSON file (certificate or verdict)")
    args = parser.parse_args()

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    try:
        data = json.loads(raw)
    except ValueError as exc:
        print(f"✗ not valid JSON: {exc}")
        return 2
    if isinstance(data, dict) and "certificate" in data and isinstance(data["certificate"], dict):
        data = data["certificate"]

    try:
        cert = Certificate(**data)
    except Exception as exc:
        print(f"✗ malformed certificate: {exc}")
        return 2

    ok = verify_certificate(cert)
    mark = "✓" if ok else "✗"
    print(f"{mark} signature {'VALID' if ok else 'INVALID (tampered or wrong key)'}")
    print(f"  decision    : {cert.decision.value}")
    print(f"  issuer      : {cert.issuer}")
    print(f"  intent_hash : {cert.intent_hash}")
    print(f"  public_key  : {cert.public_key_hex}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
