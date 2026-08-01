import os
from dotenv import load_dotenv

from .constants import (
    autopay_allowed,
    fee_amount_sats,
    fee_send_allowed,
    max_daily_payment_sats,
    max_payment_sats,
    min_payment_sats,
)
from .lightning import LNDClient
from .models import (
    Invoice,
    PaymentResult,
    OnChainSendResult,
    LightningBalance,
    ChannelBalance,
)
from .spend_ledger import assert_can_spend, record_spend

load_dotenv()


def _invoice_amount_sats(decoded: dict) -> int:
    """Extract sat amount from lncli/gRPC decodepayreq dict."""
    for key in ("num_satoshis", "num_sats", "amt_sat"):
        if decoded.get(key) is not None:
            try:
                return int(decoded[key])
            except (TypeError, ValueError):
                pass
    # msat fields
    for key in ("num_msat", "amt_msat"):
        if decoded.get(key) is not None:
            try:
                return int(decoded[key]) // 1000
            except (TypeError, ValueError):
                pass
    return 0


class AgentBitcoinClient:
    def __init__(self):
        self.lnd = LNDClient()  # No arguments needed now

        self.fee_wallet_address = os.getenv("FEE_WALLET_ADDRESS")
        self.fee_amount_sats = fee_amount_sats()
        # Also accept FEE_SATS as alias used by backend
        if (
            os.getenv("FEE_AMOUNT_SATS", "").strip() == ""
            and os.getenv("FEE_SATS", "").strip()
        ):
            self.fee_amount_sats = int(os.getenv("FEE_SATS", "1000"))
        self.min_payment_sats = min_payment_sats()
        self.max_payment_sats = max_payment_sats()
        self.max_daily_payment_sats = max_daily_payment_sats()

    def create_invoice(
        self, memo: str, amount_sats: int, expiry_seconds: int = 3600
    ) -> Invoice:
        if amount_sats < self.min_payment_sats:
            raise ValueError(f"Minimum payment is {self.min_payment_sats} sats")
        if amount_sats > self.max_payment_sats:
            raise ValueError(f"Maximum payment is {self.max_payment_sats} sats")
        return self.lnd.create_invoice(memo, amount_sats, expiry_seconds)

    def pay_invoice(
        self, payment_request: str, fee_limit_sats: int = 200
    ) -> PaymentResult:
        if not payment_request:
            raise ValueError("Payment request is required")
        if not autopay_allowed():
            raise RuntimeError(
                "Lightning pay blocked: set AGENT_BITCOIN_ALLOW_AUTOPAY=1 "
                "(required on mainnet; optional kill-switch on lab nets with =0). "
                "See docs/mainnet-pilot.md Phase 2."
            )

        amount_sats = 0
        try:
            decoded = self.lnd.decode_pay_req(payment_request.strip())
            amount_sats = _invoice_amount_sats(decoded)
        except Exception:
            # If decode fails, still attempt pay but daily/single caps use post-pay amount
            decoded = {}

        if amount_sats > 0:
            if amount_sats < self.min_payment_sats:
                raise ValueError(
                    f"Invoice amount {amount_sats} below minimum {self.min_payment_sats}"
                )
            if amount_sats > self.max_payment_sats:
                raise ValueError(
                    f"Invoice amount {amount_sats} above maximum {self.max_payment_sats}"
                )
            assert_can_spend(amount_sats, self.max_daily_payment_sats)

        result = self.lnd.pay_invoice(
            payment_request.strip(), fee_limit_sats=fee_limit_sats
        )
        if result.success:
            recorded = amount_sats or int(result.amount or 0)
            if recorded > 0:
                record_spend(recorded, payment_hash=result.payment_hash)
        return result

    def send_onchain(self, address: str, amount_sats: int) -> OnChainSendResult:
        if not fee_send_allowed():
            raise RuntimeError(
                "On-chain fee/send blocked on mainnet unless "
                "AGENT_BITCOIN_ALLOW_MAINNET_FEE=1 (pilot default off)."
            )
        if not address:
            raise ValueError("Destination address is required")
        if amount_sats <= 0:
            raise ValueError("Amount must be positive")
        return self.lnd.send_coins(address, amount_sats)

    def collect_transaction_fee(self) -> OnChainSendResult:
        if not fee_send_allowed():
            raise RuntimeError(
                "Fee collection blocked on mainnet unless "
                "AGENT_BITCOIN_ALLOW_MAINNET_FEE=1 (pilot default off)."
            )
        if not self.fee_wallet_address:
            raise RuntimeError("FEE_WALLET_ADDRESS not configured in .env")
        return self.send_onchain(self.fee_wallet_address, self.fee_amount_sats)

    def get_balance(self) -> LightningBalance:
        return self.lnd.get_balance()

    def get_channel_balance(self) -> ChannelBalance:
        return self.lnd.get_channel_balance()


def create_client() -> AgentBitcoinClient:
    """Factory function"""
    return AgentBitcoinClient()
