"""
Agent-Bitcoin SDK
=================

A Python library for Lightning Network payments between autonomous AI agents.
"""

__version__ = "0.1.0"

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

# Optional: Create a default client factory for quick usage
def create_client(
    macaroon_payment_decision: str = "/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon",
    macaroon_bitcoin: str = "/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon",
    container_payment_decision: str = "agent-payment-decision-lnd",
    container_bitcoin: str = "agent-bitcoin-lnd",
) -> AgentBitcoinClient:
    """Convenience function to create a client with default paths."""
    config = LightningConfig(
        macaroon_payment_decision=macaroon_payment_decision,
        macaroon_bitcoin=macaroon_bitcoin,
        container_payment_decision=container_payment_decision,
        container_bitcoin=container_bitcoin,
    )
    return AgentBitcoinClient(config)