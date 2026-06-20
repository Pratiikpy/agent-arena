"""Verdict, GateResult, and the signed Certificate the firewall issues.

The firewall's output is a :class:`Verdict`: a decision (ALLOW / ALLOW_CAPPED /
REJECT), the list of gate results that produced it, the effective (possibly capped)
notional, and a tamper-evident :class:`Certificate` signed with the arena's Ed25519
key. Anyone holding the public key can verify a certificate offline.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class Decision(str, Enum):
    """Firewall ruling on a proposed trade."""

    ALLOW = "ALLOW"
    ALLOW_CAPPED = "ALLOW_CAPPED"  # permitted, but notional reduced to the cap
    REJECT = "REJECT"


class GateResult(BaseModel):
    """Outcome of a single risk gate."""

    model_config = ConfigDict(frozen=True)

    gate: str
    passed: bool
    detail: str = ""
    limit: float | None = None
    attempted: float | None = None


class Certificate(BaseModel):
    """A signed attestation of a firewall decision.

    The signature covers the canonical JSON of every field except ``signature_hex``
    and ``public_key_hex``. Verification recomputes that canonical payload and
    checks it against the public key, so a certificate cannot be altered after issue.
    """

    model_config = ConfigDict(frozen=True)

    version: int = 1
    intent_hash: str  # sha256 of the canonical intent
    decision: Decision
    effective_notional_usd: float | None
    issued_at: str  # ISO-8601 UTC
    issuer: str  # short fingerprint of the signing public key
    nonce: str
    signature_hex: str = ""
    public_key_hex: str = ""


class Verdict(BaseModel):
    """The firewall's full response for one intent."""

    model_config = ConfigDict(frozen=True)

    decision: Decision
    reason: str
    gates: tuple[GateResult, ...]
    effective_notional_usd: float | None
    certificate: Certificate | None = None

    @property
    def allowed(self) -> bool:
        """Whether the trade may proceed (possibly at a reduced notional)."""
        return self.decision in (Decision.ALLOW, Decision.ALLOW_CAPPED)

    @property
    def first_failure(self) -> GateResult | None:
        """The first failing gate, if any (the binding reason for a REJECT)."""
        return next((g for g in self.gates if not g.passed), None)
