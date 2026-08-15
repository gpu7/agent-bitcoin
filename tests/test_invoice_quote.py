"""Explicit invoice quote package (payee → payer) for independent agents."""

from unittest.mock import MagicMock, patch

import pytest

from agent_bitcoin.models import InvoiceQuote


def test_create_invoice_quote_matches_requested(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.create_invoice.return_value = MagicMock(
            payment_request="lntbs20u1test",
            r_hash="ab" * 16,
            payment_hash="ab" * 16,
        )
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        q = c.create_invoice_quote(memo="svc", amount_sats=2000)
        assert q.amount_sats == 2000
        assert q.total_cost_sats == 2000
        assert q.payment_request.startswith("lntbs")
        assert q.network == "signet"
        mock_lnd.create_invoice.assert_called_once()
        assert mock_lnd.create_invoice.call_args[0][1] == 2000


def test_validate_quote_rejects_bolt11_mismatch(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.decode_pay_req.return_value = {"num_satoshis": "9999"}
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        quote = InvoiceQuote(
            payment_request="lntbs20u1x",
            amount_sats=2000,
            total_cost_sats=2000,
        )
        with pytest.raises(ValueError, match="BOLT11 amount"):
            c.validate_invoice_quote(quote)


def test_validate_quote_rejects_bad_total(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        quote = InvoiceQuote(
            payment_request="lntbs20u1x",
            amount_sats=2000,
            total_cost_sats=2500,
        )
        with pytest.raises(ValueError, match="total_cost_sats"):
            c.validate_invoice_quote(quote)


def test_build_payer_decision_inputs_ok(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.decode_pay_req.return_value = {
            "num_satoshis": "2000",
            "destination": "02abc",
            "description": "svc",
        }
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        quote = InvoiceQuote(
            payment_request="lntbs20u1x",
            amount_sats=2000,
            total_cost_sats=2000,
            memo="svc",
        )
        inputs = c.build_payer_decision_inputs(quote, routing_fee_limit_sats=200)
        assert inputs.quote_valid is True
        assert inputs.amount_sats == 2000
        assert inputs.total_cost_sats == 2000
        assert inputs.routing_fee_limit_sats == 200
        assert inputs.destination == "02abc"


def test_build_payer_decision_inputs_invalid(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.decode_pay_req.return_value = {"num_satoshis": "1"}
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        quote = {
            "payment_request": "lntbs20u1x",
            "amount_sats": 2000,
            "total_cost_sats": 2000,
        }
        inputs = c.build_payer_decision_inputs(quote)
        assert inputs.quote_valid is False
        assert inputs.validation_error


def test_api_invoice_returns_quote(clear_payment_env, monkeypatch):
    monkeypatch.setenv("AGENT_BITCOIN_API_KEY", "test-key-for-unit-tests")
    import backend.main as backend_main
    from fastapi.testclient import TestClient

    backend_main.API_KEY = "test-key-for-unit-tests"
    backend_main.MIN_PAYMENT_SATS = 2000
    backend_main.MAX_INVOICE_SATS = 1_000_000
    backend_main.client = MagicMock()
    backend_main.client.create_invoice_quote.return_value = InvoiceQuote(
        payment_request="lntbs20u1test",
        amount_sats=2000,
        total_cost_sats=2000,
        memo="ok",
        r_hash="rr",
        payment_hash="rr",
        network="signet",
    )
    client = TestClient(backend_main.app)
    r = client.post(
        "/invoices",
        json={"memo": "ok", "amount_sats": 2000},
        headers={"X-API-Key": "test-key-for-unit-tests"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["payment_request"] == "lntbs20u1test"
    assert body["amount_sats"] == 2000
    assert body["total_cost_sats"] == 2000
    assert "platform_fee_sats" not in body
    assert "transaction_fee_sats" not in body
    assert "collection" not in body
