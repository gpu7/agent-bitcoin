from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime


class LightningConfig(BaseModel):
    """Configuration for connecting to Lightning node."""
    host: str = Field("localhost", description="LND REST host")
    port: int = Field(8080, description="LND REST port")
    macaroon: str = Field(..., description="Base64 encoded macaroon")
    cert: Optional[str] = Field(None, description="TLS certificate (if using HTTPS)")
    network: Literal["regtest", "testnet", "mainnet"] = "regtest"


class Invoice(BaseModel):
    """Lightning Invoice model."""
    payment_request: str
    r_hash: str
    amount: int = Field(..., gt=0, description="Amount in satoshis")
    memo: Optional[str] = None
    expiry: int = 3600  # seconds
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Payment(BaseModel):
    """Payment request model."""
    payment_request: str
    amount: Optional[int] = None  # Only needed if invoice has no amount
    fee_limit: int = 100  # sats


class PaymentResult(BaseModel):
    """Result of a payment attempt."""
    success: bool
    status: str = Field(..., description="SUCCEEDED | FAILED | IN_FLIGHT")
    amount: int
    payment_hash: str
    preimage: Optional[str] = None
    fee: int = 0
    error: Optional[str] = None
    raw_response: Optional[str] = None


class InvoiceCreationResult(BaseModel):
    """Result when creating an invoice."""
    payment_request: str
    r_hash: str
    amount: int
    memo: Optional[str] = None
    expiry: int


# Convenience type aliases
LightningNetwork = Literal["regtest", "testnet", "mainnet"]
