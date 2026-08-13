"""
ABT-004 — transaction fee deposit to fee wallet (unit / mock).

Live on-chain confirmation remains an integration concern
(test_aws_integration.py / regtest or signet with --skip-fee as needed).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_bitcoin.constants import DEFAULT_FEE_AMOUNT_SATS


def test_abt004_client_collect_fee_sends_configured_amount(
    clear_payment_env, monkeypatch
):
    monkeypatch.setenv("FEE_WALLET_ADDRESS", "bcrt1qfeeexampleaddress000000000000000")
    monkeypatch.delenv("FEE_AMOUNT_SATS", raising=False)
    monkeypatch.delenv("FEE_SATS", raising=False)

    with patch("agent_bitcoin.client.LNDClient") as mock_lnd_cls:
        mock_lnd = MagicMock()
        mock_lnd.send_coins.return_value = MagicMock(txid="abc123", success=True)
        mock_lnd_cls.return_value = mock_lnd

        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        assert client.fee_amount_sats == DEFAULT_FEE_AMOUNT_SATS
        result = client.collect_transaction_fee()
        assert result.success is True
        mock_lnd.send_coins.assert_called_once_with(
            "bcrt1qfeeexampleaddress000000000000000",
            DEFAULT_FEE_AMOUNT_SATS,
        )


def test_abt004_client_fee_requires_address(clear_payment_env, monkeypatch):
    monkeypatch.delenv("FEE_WALLET_ADDRESS", raising=False)
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd_cls:
        mock_lnd_cls.return_value = MagicMock()
        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        with pytest.raises(RuntimeError, match="FEE_WALLET_ADDRESS"):
            client.collect_transaction_fee()


def test_abt004_api_send_fee_amount(clear_payment_env, monkeypatch):
    monkeypatch.setenv("AGENT_BITCOIN_API_KEY", "fee-test-key")
    monkeypatch.setenv("FEE_ADDRESS", "bcrt1qfeeexampleaddress000000000000000")
    monkeypatch.setenv("FEE_SATS", str(DEFAULT_FEE_AMOUNT_SATS))

    import backend.main as backend_main

    backend_main.API_KEY = "fee-test-key"
    backend_main.FEE_ADDRESS = "bcrt1qfeeexampleaddress000000000000000"
    backend_main.FEE_SATS = DEFAULT_FEE_AMOUNT_SATS
    backend_main.MAX_FEE_SEND_SATS = 100_000
    backend_main.client = MagicMock()
    backend_main.client.fee_wallet_address = None
    backend_main.client.fee_amount_sats = DEFAULT_FEE_AMOUNT_SATS
    backend_main.client.send_onchain.return_value = MagicMock(txid="fee-txid-1")

    client = TestClient(backend_main.app)
    r = client.post(
        "/send-fee",
        headers={"X-API-Key": "fee-test-key"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["amount_sats"] == DEFAULT_FEE_AMOUNT_SATS
    assert body["txid"] == "fee-txid-1"
    backend_main.client.send_onchain.assert_called_once_with(
        "bcrt1qfeeexampleaddress000000000000000",
        DEFAULT_FEE_AMOUNT_SATS,
    )


def test_default_platform_fee_is_21_sats() -> None:
    """Canonical default (not env override) is 21 sats, not the 2,000 min pay."""
    assert DEFAULT_FEE_AMOUNT_SATS == 21


def test_invoice_quote_adds_default_21_sat_fee(clear_payment_env, monkeypatch):
    monkeypatch.delenv("FEE_AMOUNT_SATS", raising=False)
    monkeypatch.delenv("FEE_SATS", raising=False)
    monkeypatch.setenv("LND_NETWORK", "regtest")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.create_invoice.return_value = MagicMock(
            payment_request="lnbcrt1testfee21",
            r_hash="ab" * 16,
            payment_hash="ab" * 16,
        )
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        assert client.fee_amount_sats == 21
        quote = client.create_invoice_quote(memo="fee-21", amount_sats=2000)
        assert quote.amount_sats == 2000
        assert quote.platform_fee_sats == 21
        assert quote.transaction_fee_sats == 21
        assert quote.total_cost_sats == 2021
