"""
Agent-Bitcoin SDK
=================

A Python library for Lightning Network payments between autonomous AI agents.
"""

__version__ = "0.1.0"

# Core
from .client import AgentBitcoinClient, create_client
from .constants import (
    DEFAULT_FEE_AMOUNT_SATS,
    DEFAULT_MAX_PAYMENT_SATS,
    DEFAULT_MIN_PAYMENT_SATS,
)
from .models import LightningConfig, Invoice, InvoiceQuote, PayerDecisionInputs

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
    "Invoice",
    "InvoiceQuote",
    "PayerDecisionInputs",
    "create_client",
    "DEFAULT_MIN_PAYMENT_SATS",
    "DEFAULT_MAX_PAYMENT_SATS",
    "DEFAULT_FEE_AMOUNT_SATS",
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
