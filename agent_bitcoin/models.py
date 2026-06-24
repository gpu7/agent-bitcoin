from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional, Dict


class LightningConfig(BaseModel):
    """Configuration for Agent Bitcoin SDK."""
    
    macaroon_payment_decision: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon")
    )
    macaroon_bitcoin: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon")
    )
    
    container_payment_decision: str = Field(default="agent-payment-decision-lnd")
    container_bitcoin: str = Field(default="agent-bitcoin-lnd")
    
    macaroon_path: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon")
    )

    class Config:
        arbitrary_types_allowed = True


class Invoice(BaseModel):
    payment_request: str
    r_hash: Optional[str] = None
    add_index: Optional[str] = None
    raw_response: Optional[Dict] = None


class InvoiceCreationResult(BaseModel):
    payment_request: str
    r_hash: Optional[str] = None
    add_index: Optional[str] = None
    raw_response: Optional[Dict] = None


class PaymentResult(BaseModel):
    success: bool
    status: str
    amount: int = 0
    payment_fee: int = 0
    payment_hash: Optional[str] = None
    preimage: Optional[str] = None
    raw_response: Optional[Dict] = None