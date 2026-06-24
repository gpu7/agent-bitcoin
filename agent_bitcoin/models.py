from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional


class LightningConfig(BaseModel):
    """Configuration for Agent Bitcoin SDK."""
    
    # Macaroon paths
    macaroon_payment_decision: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon"),
        description="Path to Agent-Payment-Decision LND macaroon"
    )
    macaroon_bitcoin: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon"),
        description="Path to Agent-Bitcoin LND macaroon"
    )
    
    # Container names (updated to match your current setup)
    container_payment_decision: str = Field(
        default="agent-payment-decision-lnd",
        description="Docker container name for the payment decision agent"
    )
    container_bitcoin: str = Field(
        default="agent-bitcoin-lnd",
        description="Docker container name for the bitcoin agent (payee)"
    )
    
    # Common macaroon path (for backward compatibility)
    macaroon_path: Path = Field(
        default=Path("/root/.lnd/data/chain/bitcoin/regtest/admin.macaroon"),
        description="Default macaroon path used by both nodes"
    )

    class Config:
        arbitrary_types_allowed = True