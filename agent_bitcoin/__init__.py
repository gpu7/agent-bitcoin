"""
Agent-Bitcoin SDK
=================

A Python library for Lightning Network payments between autonomous AI agents.
"""

__version__ = "0.1.0"

# Core
from .client import AgentBitcoinClient, create_client
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

# Intelligent Agents (kept for future use)
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
