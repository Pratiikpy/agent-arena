"""A tiny client for integrating any bot with the Agent Arena firewall.

This is the Track-2 "another developer can integrate it in minutes" surface. A third-party
agent vets every trade through one call and acts only on an ALLOW / ALLOW_CAPPED — and can
independently verify the signed certificate, with no trust in the server:

    from bitarena.client import FirewallClient

    fw = FirewallClient("https://bitarena.vercel.app")
    v = fw.vet("BTCUSDT", "buy", notional_usd=50)
    if v.allowed:
        place_my_order(symbol="BTCUSDT", side="buy", notional=v.effective_notional_usd)
    assert v.verify(fw.issuer_key())   # cert is intact AND signed by this arena

Only depends on ``httpx`` for transport; certificate verification reuses the in-package
Ed25519 check (fully offline). ``base_url`` defaults to the public deployment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from .domain.verdict import Certificate
from .firewall import verify_certificate

DEFAULT_BASE_URL = "https://bitarena.vercel.app"


@dataclass(frozen=True)
class FirewallVerdict:
    """The firewall's ruling on one proposed trade."""

    decision: str
    effective_notional_usd: float | None
    reason: str
    certificate: dict[str, Any] | None = None
    server_certificate_valid: bool | None = None
    gates: list[dict] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        """True for ALLOW / ALLOW_CAPPED — the trade may be placed (at the effective size)."""
        return self.decision in ("ALLOW", "ALLOW_CAPPED")

    def verify(self, expected_public_key_hex: str | None = None) -> bool:
        """Independently verify the signed certificate offline. Pass the arena's published
        issuer key (``FirewallClient.issuer_key()``) to also confirm authenticity — that this
        exact arena signed it, not a forger. Returns False if there is no certificate."""
        if not self.certificate:
            return False
        try:
            cert = Certificate(**self.certificate)
        except Exception:
            return False
        return verify_certificate(cert, expected_public_key_hex=expected_public_key_hex)


class FirewallClient:
    """Thin HTTP client for the firewall. Reuse one instance; it keeps a connection pool."""

    def __init__(
        self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 10.0, http_client: Any = None
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # http_client is an injection seam for tests (e.g. starlette's TestClient over the app)
        self._http = http_client or httpx.Client(base_url=self.base_url, timeout=timeout)
        self._issuer_key: str | None = None

    # -- core ----------------------------------------------------------------

    def vet(
        self,
        symbol: str,
        side: str,
        *,
        notional_usd: float | None = None,
        quantity: float | None = None,
        instrument: str = "spot",
        leverage: float = 1.0,
        equity_usd: float = 10_000.0,
        current_exposure_usd: float = 0.0,
        agent_id: str = "external-agent",
    ) -> FirewallVerdict:
        """Vet a proposed trade through ``POST /firewall`` and return a signed verdict."""
        payload = {
            "agent_id": agent_id, "symbol": symbol, "side": side, "instrument": instrument,
            "notional_usd": notional_usd, "quantity": quantity, "leverage": leverage,
            "equity_usd": equity_usd, "current_exposure_usd": current_exposure_usd,
        }
        r = self._http.post("/firewall", json={k: v for k, v in payload.items() if v is not None})
        r.raise_for_status()
        d = r.json()
        return FirewallVerdict(
            decision=d["decision"],
            effective_notional_usd=d.get("effective_notional_usd"),
            reason=d.get("reason", ""),
            certificate=d.get("certificate"),
            server_certificate_valid=d.get("certificate_valid"),
            gates=d.get("gates", []),
        )

    def issuer_key(self) -> str:
        """The arena's published Ed25519 public key (cached) for pinning authenticity."""
        if self._issuer_key is None:
            r = self._http.get("/pubkey")
            r.raise_for_status()
            self._issuer_key = r.json()["public_key_hex"]
        return self._issuer_key

    # -- convenience ---------------------------------------------------------

    def health(self) -> dict:
        r = self._http.get("/health")
        r.raise_for_status()
        return r.json()

    def pulse(self) -> dict:
        """The live signed heartbeat (latest quote + a fresh verdict + market regime)."""
        r = self._http.get("/pulse")
        r.raise_for_status()
        return r.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "FirewallClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
