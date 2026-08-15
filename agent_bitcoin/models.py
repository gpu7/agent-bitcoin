from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import os
from dotenv import load_dotenv


class Invoice(BaseModel):
    payment_request: str
    r_hash: str
    payment_hash: str


class InvoiceQuote(BaseModel):
    """
    Explicit quote package from the payee to the payer (independent agents).

    amount_sats is the requested service amount. BOLT11 and total_cost_sats
    equal that amount (no platform fee).
    """

    payment_request: str
    amount_sats: int
    total_cost_sats: int
    memo: str = ""
    r_hash: str = ""
    payment_hash: str = ""
    # Network hint only (informational)
    network: str = ""


class PayerDecisionInputs(BaseModel):
    """Structured inputs for a payer agent (and PaymentDecisionAgent)."""

    payment_request: str
    amount_sats: int
    total_cost_sats: int
    routing_fee_limit_sats: int
    quote_valid: bool
    validation_error: Optional[str] = None
    memo: str = ""
    destination: str = ""


class PaymentResult(BaseModel):
    success: bool
    payment_hash: Optional[str] = None
    preimage: Optional[str] = None
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
