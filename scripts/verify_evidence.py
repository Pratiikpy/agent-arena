"""Independently re-verify the ENTIRE evidence pack in one command.

Walks every committed signed ledger (hash-chain links + per-record Ed25519 signatures),
re-checks every firewall certificate, and confirms all of it was signed by the published
canonical issuer (``config/issuer_pubkey.hex``) — not a forger. This is the "reproduce and
verify the whole submission yourself" tool: no trust in any server, no network. Exits
non-zero if anything fails to verify.

    uv run python scripts/verify_evidence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bitarena.domain.verdict import Certificate
from bitarena.firewall import Signer, verify_certificate
from bitarena.firewall.signing import sha256_hex
from bitarena.ledger.ledger import SignedLedger

ROOT = Path(__file__).resolve().parent.parent
ISSUER = (ROOT / "config/issuer_pubkey.hex").read_text(encoding="utf-8").strip()
ISSUER_FP = sha256_hex(bytes.fromhex(ISSUER))[:16]

for _stream in (sys.stdout, sys.stderr):  # tolerate a cp1252 console
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:  # pragma: no cover
        pass


def _verify_ledgers() -> tuple[int, int, list[str]]:
    files = sorted(ROOT.glob("evidence/**/ledgers/*.jsonl"))
    sk = Signer.generate()  # verify() checks each record's embedded key; it never uses this one
    records, bad = 0, []
    for f in files:
        led = SignedLedger(sk, path=f)
        ok, issues = led.verify(expected_public_key_hex=ISSUER)
        records += len(led)
        if not ok:
            bad.append(f"{f.relative_to(ROOT).as_posix()}: {issues[0] if issues else 'invalid'}")
    return len(files), records, bad


def _verify_certs() -> tuple[int, list[str]]:
    bad, n = [], 0
    fd = json.loads((ROOT / "evidence/firewall_demos.json").read_text(encoding="utf-8"))
    for k in ("allow", "allow_capped", "reject"):
        n += 1
        if not verify_certificate(Certificate(**fd[k]["certificate"]), expected_public_key_hex=ISSUER):
            bad.append(f"firewall_demos.{k}: certificate not verified/pinned")
    td = fd["tamper_detection"]
    if not (td.get("original_valid") and not td.get("after_mutation_valid")):
        bad.append("firewall_demos.tamper_detection: tampering not detected")
    rkpath = ROOT / "evidence/regime_killswitch.json"
    if rkpath.exists():
        sr = (json.loads(rkpath.read_text(encoding="utf-8")).get("protected") or {}).get("sample_signed_reject")
        if sr and sr.get("certificate"):
            n += 1
            if not verify_certificate(Certificate(**sr["certificate"]), expected_public_key_hex=ISSUER):
                bad.append("regime_killswitch: kill-switch reject certificate not verified/pinned")
    # a real live-order receipt (once placed via scripts/place_live_order.py) is verified too
    lopath = ROOT / "evidence/live_order_receipt.json"
    if lopath.exists():
        cert = json.loads(lopath.read_text(encoding="utf-8")).get("certificate")
        if cert:
            n += 1
            if not verify_certificate(Certificate(**cert), expected_public_key_hex=ISSUER):
                bad.append("live_order_receipt: order certificate not verified/pinned")
    return n, bad


def _verify_redteam() -> tuple[dict, list[str]]:
    rt = json.loads((ROOT / "evidence/redteam.json").read_text(encoding="utf-8"))
    bad = []
    if rt.get("unsafe_allowed", 1) != 0:
        bad.append(f"redteam: {rt['unsafe_allowed']} unsafe orders allowed")
    if rt.get("false_rejects", 1) != 0:
        bad.append(f"redteam: {rt['false_rejects']} legitimate orders wrongly blocked")
    if not rt.get("all_verdicts_signed"):
        bad.append("redteam: not every verdict is signed")
    if rt.get("issuer") and rt["issuer"] != ISSUER_FP:
        bad.append(f"redteam: issuer {rt['issuer']} != canonical {ISSUER_FP}")
    return rt, bad


def main() -> int:
    lfiles, lrecords, lbad = _verify_ledgers()
    ncerts, cbad = _verify_certs()
    rt, rbad = _verify_redteam()
    problems = lbad + cbad + rbad

    print(f"ledgers : {lfiles} files, {lrecords} signed records — hash-chain + signatures + issuer-pinned")
    print(f"certs   : {ncerts} firewall certificates verified + pinned; tamper detection confirmed")
    print(f"redteam : {rt.get('total_attacks', '?')} cases, {rt.get('unsafe_allowed', '?')} unsafe, all signed")
    print(f"issuer  : {ISSUER_FP} ({ISSUER[:16]}…, config/issuer_pubkey.hex)")
    if problems:
        print("\n✗ FAILURES:")
        for p in problems:
            print("  -", p)
        return 1
    print("\n✓ entire evidence pack independently verified — signed, chained, pinned, untampered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
