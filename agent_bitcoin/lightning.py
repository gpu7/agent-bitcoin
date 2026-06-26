import os
from typing import Optional

from .exceptions import LNDException
from .models import (
    Invoice,
    PaymentResult,
    OnChainSendResult,
    LightningBalance,
    ChannelBalance,
)

# Use the high-level client from lnd-grpc-client
from lndgrpc import LNDClient as RawLNDClient


class LNDClient:
    """Wrapper around lndgrpc.LNDClient"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 10009,
        macaroon_path: Optional[str] = None,
        tls_cert_path: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.macaroon_path = macaroon_path or os.getenv("LND_MACAROON_PATH")
        self.tls_cert_path = tls_cert_path or os.getenv("LND_TLS_CERT_PATH")

        self._client = None
        self._connect()

    def _connect(self):
        """Connect using lndgrpc high-level client"""
        try:
            tls_path = os.path.expanduser(str(self.tls_cert_path))
            mac_path = os.path.expanduser(str(self.macaroon_path))

            print(f"🔑 Loading TLS from: {tls_path}")
            print(f"🔑 Loading macaroon from: {mac_path}")

            # Fixed parameter names for this package version
            self._client = RawLNDClient(
                cert_filepath=tls_path,
                macaroon_filepath=mac_path,
            )

            print("✅ Successfully connected to LND via lndgrpc!")

        except Exception as e:
            raise LNDException(f"Failed to connect to LND: {str(e)}")

    # ====================== LIGHTNING METHODS ======================

    def create_invoice(self, memo: str, amount_sats: int, expiry_seconds: int = 3600) -> Invoice:
        try:
            resp = self._client.add_invoice(memo=memo, value=amount_sats, expiry=expiry_seconds)
            return Invoice(
                payment_request=resp.payment_request,
                r_hash=resp.r_hash.hex(),
                payment_hash=resp.r_hash.hex(),
            )
        except Exception as e:
            raise LNDException(f"Failed to create invoice: {str(e)}")

    def pay_invoice(self, payment_request: str) -> PaymentResult:
        try:
            resp = self._client.send_payment_sync(payment_request=payment_request)
            success = resp.status == "SUCCEEDED"

            return PaymentResult(
                success=success,
                payment_hash=resp.payment_hash.hex() if hasattr(resp, 'payment_hash') else None,
                amount=getattr(resp, 'value_sat', 0),
                status=getattr(resp, 'status', 'UNKNOWN'),
            )
        except Exception as e:
            raise LNDException(f"Failed to pay invoice: {str(e)}")

    def send_coins(self, address: str, amount_sats: int) -> OnChainSendResult:
        try:
            resp = self._client.send_coins(addr=address, amount=amount_sats)
            return OnChainSendResult(txid=resp.txid, success=True)
        except Exception as e:
            raise LNDException(f"Failed to send on-chain: {str(e)}")

    def get_balance(self) -> LightningBalance:
        try:
            resp = self._client.wallet_balance()
            return LightningBalance(
                total_balance=str(resp.total_balance),
                confirmed_balance=str(resp.confirmed_balance),
                unconfirmed_balance=str(resp.unconfirmed_balance),
            )
        except Exception as e:
            raise LNDException(f"Failed to get balance: {str(e)}")

    def get_channel_balance(self) -> ChannelBalance:
        try:
            resp = self._client.channel_balance()
            return ChannelBalance(
                local_balance=resp.local_balance,
                remote_balance=resp.remote_balance,
            )
        except Exception as e:
            raise LNDException(f"Failed to get channel balance: {str(e)}")


__all__ = ["LNDClient"]