"""Basic client factory tests."""

from unittest.mock import MagicMock, patch

from agent_bitcoin import (
    DEFAULT_MAX_PAYMENT_SATS,
    DEFAULT_MIN_PAYMENT_SATS,
    create_client,
)


def test_create_client(clear_payment_env):
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd:
        mock_lnd.return_value = MagicMock()
        client = create_client()
        assert client is not None
        assert client.min_payment_sats == DEFAULT_MIN_PAYMENT_SATS
        assert client.max_payment_sats == DEFAULT_MAX_PAYMENT_SATS
        assert not hasattr(client, "fee_amount_sats")


def test_pay_invoice_requires_request(clear_payment_env):
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd:
        mock_lnd.return_value = MagicMock()
        client = create_client()
        import pytest

        with pytest.raises(ValueError, match="Payment request"):
            client.pay_invoice("")


def test_module_pay_invoice_requires_request(clear_payment_env):
    import pytest

    from agent_bitcoin import pay_invoice

    with patch("agent_bitcoin.client.LNDClient") as mock_lnd:
        mock_lnd.return_value = MagicMock()
        with pytest.raises(ValueError, match="Payment request"):
            pay_invoice("")


def test_module_pay_invoice_forwards_arguments(clear_payment_env):
    from agent_bitcoin import pay_invoice
    from agent_bitcoin.client import AgentBitcoinClient

    sentinel = object()

    def fake(self, payment_request, fee_limit_sats=200, *, minimum_sats=None):
        assert payment_request == "lnbc"
        assert fee_limit_sats == 50
        assert minimum_sats == 100
        return sentinel

    with patch("agent_bitcoin.client.LNDClient") as mock_lnd:
        mock_lnd.return_value = MagicMock()
        with patch.object(AgentBitcoinClient, "pay_invoice", fake):
            assert pay_invoice("lnbc", fee_limit_sats=50, minimum_sats=100) is sentinel
