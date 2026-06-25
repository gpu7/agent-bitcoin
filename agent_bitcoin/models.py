from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import os


class LightningConfig(BaseModel):
    """Configuration for Agent Bitcoin SDK with .env support."""

    # Container names
    container_payment_decision: str = Field(
        default="agent-payment-decision-lnd",
        description="Docker container name for payment decision node"
    )
    container_bitcoin: str = Field(
        default="agent-bitcoin-lnd",
        description="Docker container name for bitcoin node (payee)"
    )

    # Macaroon paths
    macaroon_payment_decision: Path = Field(
        default=Path("/tmp/agent-payment-decision.macaroon")
    )
    macaroon_bitcoin: Path = Field(
        default=Path("/tmp/agent-bitcoin.macaroon")
    )

    # Common macaroon path (for backward compatibility)
    macaroon_path: Path = Field(
        default=Path("/tmp/agent-payment-decision.macaroon")
    )

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "LightningConfig":
        """Load config from .env file with fallback to defaults."""
        load_dotenv(env_file)
        
        return cls(
            container_payment_decision=os.getenv(
                "CONTAINER_PAYMENT_DECISION", "agent-payment-decision-lnd"
            ),
            container_bitcoin=os.getenv(
                "CONTAINER_BITCOIN", "agent-bitcoin-lnd"
            ),
            macaroon_payment_decision=Path(os.getenv(
                "MACAROON_PAYMENT_DECISION", "/tmp/agent-payment-decision.macaroon"
            )),
            macaroon_bitcoin=Path(os.getenv(
                "MACAROON_BITCOIN", "/tmp/agent-bitcoin.macaroon"
            )),
        )

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