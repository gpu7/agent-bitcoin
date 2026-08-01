"""
ABT-001 / ABT-002 / ABT-003 — payment amount bounds.

Unit tests for client invoice validation and backend API limits.
No live Lightning required.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_bitcoin.constants import (
    DEFAULT_MAX_PAYMENT_SATS,
    DEFAULT_MIN_PAYMENT_SATS,
)


# --- Client (SDK) ---


def test_abt001_client_normal_amount_reaches_lnd(clear_payment_env, payment_limits):
    """In-range amount is accepted and forwarded to LND."""
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd_cls:
        mock_lnd = MagicMock()
        mock_lnd.create_invoice.return_value = MagicMock(
            payment_request="lnbcrt1test", r_hash="ab", payment_hash="cd"
        )
        mock_lnd_cls.return_value = mock_lnd

        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        mid = (payment_limits["min"] + payment_limits["max"]) // 2
        inv = client.create_invoice(memo="nominal", amount_sats=mid)
        assert inv.payment_request.startswith("lnbcrt")
        mock_lnd.create_invoice.assert_called_once()
        args = mock_lnd.create_invoice.call_args[0]
        assert args[1] == mid


def test_abt002_client_below_minimum(clear_payment_env, payment_limits):
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd_cls:
        mock_lnd_cls.return_value = MagicMock()
        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        with pytest.raises(ValueError, match="Minimum payment"):
            client.create_invoice(memo="tiny", amount_sats=payment_limits["min"] - 1)
        mock_lnd_cls.return_value.create_invoice.assert_not_called()


def test_abt003_client_above_maximum(clear_payment_env, payment_limits):
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd_cls:
        mock_lnd_cls.return_value = MagicMock()
        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        with pytest.raises(ValueError, match="Maximum payment"):
            client.create_invoice(memo="huge", amount_sats=payment_limits["max"] + 1)
        mock_lnd_cls.return_value.create_invoice.assert_not_called()


def test_shared_defaults_one_million_max(clear_payment_env):
    assert DEFAULT_MIN_PAYMENT_SATS == 2_000
    assert DEFAULT_MAX_PAYMENT_SATS == 1_000_000
    from agent_bitcoin.constants import max_invoice_sats, payment_decision_max_sats

    assert max_invoice_sats() == 1_000_000
    assert payment_decision_max_sats() == 1_000_000


# --- Backend API ---


@pytest.fixture
def api_client(clear_payment_env, monkeypatch):
    monkeypatch.setenv("AGENT_BITCOIN_API_KEY", "test-key-for-unit-tests")
    # Re-import app with env applied — set module-level constants after import
    import backend.main as backend_main

    backend_main.API_KEY = "test-key-for-unit-tests"
    backend_main.MIN_PAYMENT_SATS = DEFAULT_MIN_PAYMENT_SATS
    backend_main.MAX_INVOICE_SATS = DEFAULT_MAX_PAYMENT_SATS
    backend_main.client = MagicMock()
    backend_main.client.create_invoice.return_value = MagicMock(
        payment_request="lnbcrt1test",
        r_hash="rr",
    )
    return TestClient(backend_main.app), backend_main


def test_abt001_api_normal_invoice(api_client, payment_limits):
    client, backend_main = api_client
    mid = 50_000
    r = client.post(
        "/invoices",
        json={"memo": "ok", "amount_sats": mid},
        headers={"X-API-Key": "test-key-for-unit-tests"},
    )
    assert r.status_code == 200
    assert r.json()["amount_sats"] == mid
    backend_main.client.create_invoice.assert_called()


def test_abt002_api_below_minimum(api_client, payment_limits):
    client, backend_main = api_client
    r = client.post(
        "/invoices",
        json={"memo": "tiny", "amount_sats": payment_limits["min"] - 1},
        headers={"X-API-Key": "test-key-for-unit-tests"},
    )
    assert r.status_code == 400
    assert "amount_sats" in r.json()["detail"].lower() or "2000" in r.json()["detail"]
    backend_main.client.create_invoice.assert_not_called()


def test_abt003_api_above_maximum(api_client, payment_limits):
    client, backend_main = api_client
    r = client.post(
        "/invoices",
        json={"memo": "huge", "amount_sats": payment_limits["max"] + 1},
        headers={"X-API-Key": "test-key-for-unit-tests"},
    )
    assert r.status_code == 400
    backend_main.client.create_invoice.assert_not_called()


def test_api_requires_key(api_client):
    client, _ = api_client
    r = client.post("/invoices", json={"memo": "x", "amount_sats": 5000})
    assert r.status_code == 401
