from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional, Dict
from dotenv import load_dotenv
import os


class LightningConfig(BaseModel):
    """Configuration for Agent Bitcoin SDK with .env support."""

    # Container names
    container_payment_decision: str = Field(
        default="agent-payment-decision-lnd",
        description="Docker container name for payment decision node",
    )
    container_bitcoin: str = Field(
        default="agent-bitcoin-lnd",
        description="Docker container name for bitcoin node (payee)",
    )

    # Macaroon paths (inside the containers)
    macaroon_payment_decision: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon")
    )
    macaroon_bitcoin: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon")
    )

    # The path actually used by _run_lnd_command
    macaroon_path: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon")
    )

    # Pydantic v2 style configuration
    model_config = {
        "arbitrary_types_allowed": True,
    }

    @classmethod
    def from_env(cls, env_file: str = ".env") -> "LightningConfig":
        """Load configuration from .env file."""
        load_dotenv(env_file)

        config = cls(
            container_payment_decision=os.getenv(
                "CONTAINER_PAYMENT_DECISION", "agent-payment-decision-lnd"
            ),
            container_bitcoin=os.getenv("CONTAINER_BITCOIN", "agent-bitcoin-lnd"),
        )
        return config


# ====================== Result Models ======================


class InvoiceCreationResult(BaseModel):
    """Result of creating a Lightning invoice."""

    payment_request: str
    r_hash: Optional[str] = None
    add_index: Optional[str] = None
    raw_response: Optional[Dict] = None


class PaymentResult(BaseModel):
    """Result of paying a Lightning invoice."""

    success: bool
    status: str
    amount: int = 0
    payment_fee: int = 0
    payment_hash: Optional[str] = None
    preimage: Optional[str] = None
    raw_response: Optional[Dict] = None
