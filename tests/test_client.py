"""Tests for the FirewallClient integration SDK (in-process ASGI transport, no network)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # SDK tests need the [api] extra (fastapi/starlette)

from starlette.testclient import TestClient  # noqa: E402

from bitarena.api.app import create_app  # noqa: E402
from bitarena.client import FirewallClient  # noqa: E402
from bitarena.domain.verdict import Certificate  # noqa: E402
from bitarena.firewall.signing import Signer  # noqa: E402


def _client() -> FirewallClient:
    app = create_app(offline=True, evidence_dir="evidence/last_run")
    return FirewallClient(http_client=TestClient(app))


def test_vet_allows_and_verifies():
    with _client() as fw:
        v = fw.vet("BTCUSDT", "buy", notional_usd=50.0)
        assert v.allowed and v.decision in ("ALLOW", "ALLOW_CAPPED")
        assert v.verify() is True                      # integrity, offline
        assert v.verify(fw.issuer_key()) is True        # authenticity vs the published key


def test_vet_oversized_is_capped():
    with _client() as fw:
        v = fw.vet("BTCUSDT", "buy", notional_usd=999_999.0)
        assert v.decision == "ALLOW_CAPPED"
        assert v.effective_notional_usd is not None and v.effective_notional_usd <= 2_000 + 1e-6


def test_vet_rejected_when_no_headroom():
    # account already at the exposure cap (equity 10k × 3x leverage = 30k) → no room → REJECT
    with _client() as fw:
        v = fw.vet("BTCUSDT", "buy", notional_usd=2_000.0, current_exposure_usd=30_000.0)
        assert not v.allowed and v.decision == "REJECT"


def test_client_rejects_a_forged_verdict():
    with _client() as fw:
        v = fw.vet("BTCUSDT", "buy", notional_usd=50.0)
        forged = Signer.generate().sign_certificate(Certificate(**v.certificate))
        bad = v.__class__(decision="ALLOW", effective_notional_usd=1e9, reason="forged",
                          certificate=forged.model_dump())
        assert bad.verify() is True                       # self-consistent (integrity holds)
        assert bad.verify(fw.issuer_key()) is False        # but NOT signed by this arena
