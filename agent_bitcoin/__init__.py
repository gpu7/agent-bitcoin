"""
Agent-Bitcoin SDK
=================

A Python library for Lightning Network payments between autonomous AI agents.
"""

__version__ = "0.1.0"

from pathlib import Path
from typing import Optional

# Core Lightning client
from .client import AgentBitcoinClient
from .models import LightningConfig

# Exceptions
from .exceptions import (
    AgentBitcoinError,
    InvoiceCreationError,
    PaymentError,
    MacaroonError,
    InsufficientBalanceError,
    NoRouteError,
)

# Intelligent Agents
from .agents.payment_decision import (
    PaymentDecisionAgent,
    create_payment_decision_agent,
    create_grok_payment_decision_agent,
    PaymentDecision,
)

# Main public API
__all__ = [
    # Core
    "AgentBitcoinClient",
    "LightningConfig",
    "create_client",
    
    # Exceptions
    "AgentBitcoinError",
    "InvoiceCreationError",
    "PaymentError",
    "MacaroonError",
    "InsufficientBalanceError",
    "NoRouteError",
    
    # Intelligent Agents
    "PaymentDecisionAgent",
    "create_payment_decision_agent",
    "create_grok_payment_decision_agent",
    "PaymentDecision",
]


def create_client(
    env_file: str = ".env",
    container_payment_decision: Optional[str] = None,
    container_bitcoin: Optional[str] = None,
    macaroon_payment_decision: Optional[str] = None,
    macaroon_bitcoin: Optional[str] = None,
) -> AgentBitcoinClient:
    """
    Create an AgentBitcoinClient with .env support.
    
    Priority: Explicit arguments > .env file > defaults
    """
    # Load from .env first
    config = LightningConfig.from_env(env_file)

    # Override with explicit parameters if provided
    if container_payment_decision:
        config.container_payment_decision = container_payment_decision
    if container_bitcoin:
        config.container_bitcoin = container_bitcoin
    if macaroon_payment_decision:
        config.macaroon_payment_decision = Path(macaroon_payment_decision)
    if macaroon_bitcoin:
        config.macaroon_bitcoin = Path(macaroon_bitcoin)

    return AgentBitcoinClient(config)