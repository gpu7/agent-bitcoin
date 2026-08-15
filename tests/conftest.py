"""Shared pytest fixtures and markers."""

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: tests that need live Docker/LND/backend (skip by default in offline CI)",
    )


@pytest.fixture
def payment_limits():
    """Canonical defaults from agent_bitcoin.constants."""
    from agent_bitcoin.constants import (
        DEFAULT_MAX_PAYMENT_SATS,
        DEFAULT_MIN_PAYMENT_SATS,
    )

    return {
        "min": DEFAULT_MIN_PAYMENT_SATS,
        "max": DEFAULT_MAX_PAYMENT_SATS,
    }


@pytest.fixture
def clear_payment_env(monkeypatch):
    """Isolate tests from developer .env overrides for limit keys."""
    for key in (
        "MIN_PAYMENT_SATS",
        "MAX_PAYMENT_SATS",
        "MAX_INVOICE_SATS",
        "PAYMENT_DECISION_MAX_SATS",
        "PAYMENT_DECISION_CONFIRM_ABOVE_SATS",
        "FEE_AMOUNT_SATS",
        "FEE_SATS",
        "MAX_FEE_SEND_SATS",
        "AGENT_BITCOIN_API_KEY",
        "LND_NETWORK",
        "LND_TRANSPORT",
        "LND_TLS_CERT_PATH",
        "LND_CERT_PATH",
        "LND_MACAROON_PATH",
        "LND_GRPC_HOST",
        "LND_GRPC_PORT",
        "AGENT_BITCOIN_ALLOW_MAINNET",
        "AGENT_BITCOIN_ALLOW_AUTOPAY",
        "AGENT_BITCOIN_ALLOW_MAINNET_FEE",
        "AGENT_BITCOIN_SPEND_LEDGER",
        "MAX_DAILY_PAYMENT_SATS",
    ):
        monkeypatch.delenv(key, raising=False)
    # Avoid real LND docker during client construction where possible
    yield
