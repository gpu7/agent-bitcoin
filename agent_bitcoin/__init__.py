"""
Agent-Bitcoin SDK
=================

A Python library for Lightning Network payments between autonomous AI agents.
"""

__version__ = "0.1.0"

from pathlib import Path
from typing import Optional

from .client import AgentBitcoinClient
from .models import (
    LightningConfig,
    Invoice,
    PaymentResult,
    InvoiceCreationResult,
)
from .exceptions import (
    AgentBitcoinError,
    InvoiceCreationError,
    PaymentError,
    MacaroonError,
    InsufficientBalanceError,
    NoRouteError,
)

# Main public API
__all__ = [
    "AgentBitcoinClient",
    "LightningConfig",
    "Invoice",
    "PaymentResult",
    "InvoiceCreationResult",
    "AgentBitcoinError",
    "InvoiceCreationError",
    "PaymentError",
    "MacaroonError",
    "InsufficientBalanceError",
    "NoRouteError",
]

# Convenience function
def create_client(
    macaroon_payment_decision: str = "/tmp/agent-payment-decision.macaroon",
    macaroon_bitcoin: str = "/tmp/agent-bitcoin.macaroon",
    container_payment_decision: str = "agent-payment-decision-lnd",
    container_bitcoin: str = "agent-bitcoin-lnd",
) -> AgentBitcoinClient:
    """Convenience function to create a client with local development defaults."""
    config = LightningConfig(
        macaroon_payment_decision=Path(macaroon_payment_decision),
        macaroon_bitcoin=Path(macaroon_bitcoin),
        container_payment_decision=container_payment_decision,
        container_bitcoin=container_bitcoin,
    )
    return AgentBitcoinClient(config)