"""Platform fee is bundled into the Lightning invoice (no on-chain fee API)."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agent_bitcoin.constants import DEFAULT_FEE_AMOUNT_SATS


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
        assert quote.collection == "lightning_bundled"
        mock_lnd.create_invoice.assert_called_once()
        assert mock_lnd.create_invoice.call_args[0][1] == 2021


def test_send_fee_route_removed(clear_payment_env, monkeypatch):
    monkeypatch.setenv("AGENT_BITCOIN_API_KEY", "fee-test-key")
    import backend.main as backend_main

    backend_main.API_KEY = "fee-test-key"
    client = TestClient(backend_main.app)
    r = client.post("/send-fee", headers={"X-API-Key": "fee-test-key"})
    assert r.status_code == 404
