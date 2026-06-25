from typing import Optional
from .client import AgentBitcoinClient
from .models import (
    PaymentResult,
    InvoiceCreationResult,
    LightningConfig,
)
from .exceptions import PaymentError


class LightningManager:
    """
    High-level Lightning operations for AI agents.
    """

    def __init__(self, config: LightningConfig):
        self.client = AgentBitcoinClient(config)

    def create_invoice(
        self, amount: int, memo: Optional[str] = None, expiry: int = 3600
    ) -> InvoiceCreationResult:
        """Create a Lightning invoice (synchronous)."""
        if amount <= 0:
            raise ValueError("Amount must be greater than 0 sats")

        return self.client.create_invoice(amount=amount, memo=memo, expiry=expiry)

    def pay_invoice(self, payment_request: str, fee_limit: int = 200) -> PaymentResult:
        """Pay a Lightning invoice."""
        if not payment_request or not payment_request.startswith("lnbc"):
            raise ValueError("Invalid payment request (must be a Lightning invoice)")

        try:
            return self.client.pay_invoice(
                payment_request=payment_request, fee_limit=fee_limit
            )
        except Exception as e:
            raise PaymentError(f"Failed to pay invoice: {str(e)}") from e

    def pay_amount(self, payment_request: str, amount: int) -> PaymentResult:
        """Pay a zero-amount invoice with a specific amount (if supported)."""
        # This can be expanded later for zero-amount invoices
        return self.pay_invoice(payment_request, fee_limit=200)

    def close(self):
        """Close underlying client."""
        self.client.close()


# Convenience alias
Lightning = LightningManager
