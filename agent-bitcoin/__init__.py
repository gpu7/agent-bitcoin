"""
Agent-Bitcoin SDK
Lightning payments between autonomous AI agents.
"""

from .client import AgentBitcoinClient
from .models import (
    Invoice,
    Payment,
    PaymentResult,
    LightningConfig,
)

__version__ = "0.1.0"
__all__ = [
    "AgentBitcoinClient",
    "Invoice",
    "Payment",
    "PaymentResult",
    "LightningConfig",
]
