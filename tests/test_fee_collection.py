"""No platform fee: BOLT11 equals the requested amount. On-chain fee API stays gone."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_invoice_quote_equals_requested_amount(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "regtest")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.create_invoice.return_value = MagicMock(
            payment_request="lnbcrt1testnofee",
            r_hash="ab" * 16,
            payment_hash="ab" * 16,
        )
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        client = AgentBitcoinClient()
        quote = client.create_invoice_quote(memo="no-fee", amount_sats=2000)
        assert quote.amount_sats == 2000
        assert quote.total_cost_sats == 2000
        mock_lnd.create_invoice.assert_called_once()
        assert mock_lnd.create_invoice.call_args[0][1] == 2000


def test_send_fee_route_removed(clear_payment_env, monkeypatch):
    monkeypatch.setenv("AGENT_BITCOIN_API_KEY", "fee-test-key")
    import backend.main as backend_main

    backend_main.API_KEY = "fee-test-key"
    client = TestClient(backend_main.app)
    r = client.post("/send-fee", headers={"X-API-Key": "fee-test-key"})
    assert r.status_code == 404
