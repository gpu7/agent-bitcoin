import pytest
from agent_bitcoin import create_client


def test_client_can_be_created():
    client = create_client()
    assert client is not None


def test_config_defaults():
    client = create_client()
    assert client.config.container_payment_decision == "agent-payment-decision-lnd"
    assert client.config.container_bitcoin == "agent-bitcoin-lnd"


def test_create_invoice_validation():
    client = create_client()
    with pytest.raises(Exception):  # Should raise for invalid amount
        client.create_invoice(memo="Test", amount_sats=0)


@pytest.mark.skip(reason="Requires running Docker containers")
def test_create_and_pay_invoice():
    client = create_client()
    invoice = client.create_invoice(memo="Test", amount_sats=3000)
    assert invoice.payment_request.startswith("lnbcrt")
