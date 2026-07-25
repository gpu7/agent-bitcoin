"""Basic client factory tests."""

from unittest.mock import MagicMock, patch

from agent_bitcoin import (
    DEFAULT_FEE_AMOUNT_SATS,
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
        assert client.fee_amount_sats == DEFAULT_FEE_AMOUNT_SATS


def test_pay_invoice_requires_request(clear_payment_env):
    with patch("agent_bitcoin.client.LNDClient") as mock_lnd:
        mock_lnd.return_value = MagicMock()
        client = create_client()
        import pytest

        with pytest.raises(ValueError, match="Payment request"):
            client.pay_invoice("")
