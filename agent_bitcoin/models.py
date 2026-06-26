from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import os
from dotenv import load_dotenv


class Invoice(BaseModel):
    payment_request: str
    r_hash: str
    payment_hash: str


class PaymentResult(BaseModel):
    success: bool
    payment_hash: Optional[str] = None
    amount: int = 0
    status: str = "UNKNOWN"


class OnChainSendResult(BaseModel):
    txid: str
    success: bool = True


class LightningBalance(BaseModel):
    total_balance: str
    confirmed_balance: str
    unconfirmed_balance: str


class ChannelBalance(BaseModel):
    local_balance: int
    remote_balance: int


class LightningConfig(BaseModel):
    """Configuration for connecting to LND"""
    host: str = "localhost"
    port: int = 10009
    tls_cert_path: Optional[Path] = None
    macaroon_path: Optional[Path] = None

    # Optional container/macaroon overrides
    container_payment_decision: Optional[str] = None
    container_bitcoin: Optional[str] = None
    macaroon_payment_decision: Optional[Path] = None
    macaroon_bitcoin: Optional[Path] = None

    @classmethod
    def from_env(cls, env_file: str = ".env"):
        """Load configuration from .env file"""
        load_dotenv(env_file)
        
        tls_path = os.getenv("LND_TLS_CERT_PATH")
        macaroon_path = os.getenv("LND_MACAROON_PATH")

        return cls(
            host=os.getenv("LND_GRPC_HOST", "localhost"),
            port=int(os.getenv("LND_GRPC_PORT", 10009)),
            tls_cert_path=Path(tls_path) if tls_path else None,
            macaroon_path=Path(macaroon_path) if macaroon_path else None,
        )