import os
from typing import Optional
from dotenv import load_dotenv

from .lightning import LNDClient
from .models import (
    Invoice, 
    PaymentResult, 
    OnChainSendResult,
    LightningBalance, 
    ChannelBalance,
    LightningConfig
)
from .exceptions import LNDException

load_dotenv()


class AgentBitcoinClient:
    def __init__(self, config: Optional[LightningConfig] = None):
        if config is None:
            config = LightningConfig.from_env()

        self.config = config
        self.lnd = LNDClient(
            host=config.host,
            port=config.port,
            macaroon_path=str(config.macaroon_path) if config.macaroon_path else None,
            tls_cert_path=str(config.tls_cert_path) if config.tls_cert_path else None,
        )

        self.fee_wallet_address = os.getenv("FEE_WALLET_ADDRESS")
        self.fee_amount_sats = int(os.getenv("FEE_AMOUNT_SATS", 1000))
        self.min_payment_sats = int(os.getenv("MIN_PAYMENT_SATS", 2000))

    def create_invoice(self, memo: str, amount_sats: int, expiry_seconds: int = 3600) -> Invoice:
        if amount_sats < self.min_payment_sats:
            raise ValueError(f"Minimum payment is {self.min_payment_sats} sats")
        return self.lnd.create_invoice(memo, amount_sats, expiry_seconds)

    def pay_invoice(self, payment_request: str) -> PaymentResult:
        if not payment_request:
            raise ValueError("Payment request is required")
        return self.lnd.pay_invoice(payment_request)

    def send_onchain(self, address: str, amount_sats: int) -> OnChainSendResult:
        if not address:
            raise ValueError("Destination address is required")
        if amount_sats <= 0:
            raise ValueError("Amount must be positive")
        return self.lnd.send_coins(address, amount_sats)

    def collect_transaction_fee(self) -> OnChainSendResult:
        if not self.fee_wallet_address:
            raise RuntimeError("FEE_WALLET_ADDRESS not configured in .env")
        return self.send_onchain(self.fee_wallet_address, self.fee_amount_sats)

    def get_balance(self) -> LightningBalance:
        return self.lnd.get_balance()

    def get_channel_balance(self) -> ChannelBalance:
        return self.lnd.get_channel_balance()


def create_client(config: Optional[LightningConfig] = None) -> AgentBitcoinClient:
    """Factory function to create client (used by backend and SDK)"""
    return AgentBitcoinClient(config)