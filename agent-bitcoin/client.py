import base64
import json
from typing import Optional
import httpx

from .models import (
    LightningConfig,
    Invoice,
    Payment,
    PaymentResult,
    InvoiceCreationResult,
)
from .exceptions import (
    AgentBitcoinError,
    LightningConnectionError,
    InvoiceCreationError,
    PaymentError,
    MacaroonError,
)


class AgentBitcoinClient:
    """
    Main client for interacting with Lightning Network (LND).
    """

    def __init__(self, config: LightningConfig):
        self.config = config
        self.base_url = f"http://{config.host}:{config.port}/v1"
        
        # Prepare macaroon header
        if not config.macaroon:
            raise MacaroonError("Macaroon is required")
        
        self.headers = {
            "Grpc-Metadata-macaroon": config.macaroon,
            "Content-Type": "application/json",
        }

        # HTTP client
        self.client = httpx.Client(timeout=30.0, verify=False)  # verify=False for regtest self-signed certs

    async def acreate_invoice(
        self, amount: int, memo: Optional[str] = None, expiry: int = 3600
    ) -> InvoiceCreationResult:
        """Async: Create a new Lightning invoice."""
        payload = {
            "value": str(amount),
            "memo": memo or "",
            "expiry": str(expiry),
        }

        try:
            response = self.client.post(
                f"{self.base_url}/invoices",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            return InvoiceCreationResult(
                payment_request=data["payment_request"],
                r_hash=data["r_hash"],
                amount=amount,
                memo=memo,
                expiry=expiry,
            )
        except httpx.HTTPStatusError as e:
            raise InvoiceCreationError(f"Failed to create invoice: {e.response.text}") from e
        except Exception as e:
            raise LightningConnectionError(f"Connection error: {str(e)}") from e

    def create_invoice(
        self, amount: int, memo: Optional[str] = None, expiry: int = 3600
    ) -> InvoiceCreationResult:
        """Sync: Create a new Lightning invoice."""
        return self.acreate_invoice(amount, memo, expiry)  # For now we call async version

    def pay_invoice(self, payment_request: str, fee_limit: int = 100) -> PaymentResult:
        """Sync: Pay a Lightning invoice."""
        payload = {
            "payment_request": payment_request,
            "fee_limit": {"fixed": str(fee_limit)},
        }

        try:
            response = self.client.post(
                f"{self.base_url}/channels/transactions",
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

            return PaymentResult(
                success=True,
                status="SUCCEEDED",
                amount=int(data.get("payment_route", {}).get("total_amt", 0)),
                payment_hash=data.get("payment_hash", ""),
                preimage=data.get("payment_preimage"),
                fee=0,  # Can be improved later
            )
        except httpx.HTTPStatusError as e:
            error_msg = e.response.text
            raise PaymentError(f"Payment failed: {error_msg}", payment_hash=None) from e
        except Exception as e:
            raise LightningConnectionError(f"Connection error while paying: {str(e)}") from e

    def close(self):
        """Close the HTTP client."""
        self.client.close()
