"""
Agent-Bitcoin SDK
Lightning Network payments for autonomous AI Agents.
"""

__version__ = "0.1.0"

from .models import (
    LightningConfig,
    Invoice,
    Payment,
    PaymentResult,
    InvoiceCreationResult,
)

from .client import AgentBitcoinClient
from .lightning import LightningManager, Lightning
from .exceptions import (
    AgentBitcoinError,
    LightningConnectionError,
    InvoiceCreationError,
    PaymentError,
    InsufficientBalanceError,
    NoRouteError,
    InvoiceExpiredError,
    MacaroonError,
    ValidationError,
)

__all__ = [
    # Main classes
    "AgentBitcoinClient",
    "LightningManager",
    "Lightning",
    
    # Models
    "LightningConfig",
    "Invoice",
    "Payment",
    "PaymentResult",
    "InvoiceCreationResult",
    
    # Exceptions
    "AgentBitcoinError",
    "LightningConnectionError",
    "InvoiceCreationError",
    "PaymentError",
    "InsufficientBalanceError",
    "NoRouteError",
    "InvoiceExpiredError",
    "MacaroonError",
    "ValidationError",
]

# Convenience alias for quick usage
Lightning = LightningManager
