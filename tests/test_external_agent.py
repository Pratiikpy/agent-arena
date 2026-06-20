"""Prove an external agent can integrate over HTTP and receives signed verdicts."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")  # API tests need the [api] extra; skip cleanly without it

from fastapi.testclient import TestClient  # noqa: E402

from bitarena.api.app import create_app  # noqa: E402
from bitarena.connectors import ReplayMarketData, synthetic_series  # noqa: E402
from bitarena.domain.market import InstrumentType  # noqa: E402
from bitarena.external_example import run_external_agent  # noqa: E402


def test_external_agent_integrates_over_http():
    client = TestClient(create_app(offline=True))

    def post_firewall(payload: dict) -> dict:
        return client.post("/firewall", json=payload).json()

    market = ReplayMarketData({"BTCUSDT": synthetic_series("BTCUSDT", n=160, seed=3, vol=0.02)})
    report = run_external_agent(post_firewall, market, symbol="BTCUSDT", instrument=InstrumentType.SPOT, steps=120)

    # every verdict the external bot acted on was signed and valid
    assert report["all_verdicts_signed"] is True
    # tallies are consistent
    assert report["allowed"] + report["allow_capped"] + report["rejected"] == report["decisions"]
