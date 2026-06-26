import os
from typing import Optional
import grpc
import codecs

from .exceptions import LNDException
from .models import (
    Invoice,
    PaymentResult,
    OnChainSendResult,
    LightningBalance,
    ChannelBalance,
)

# Pure gRPC imports
import lightning_pb2 as ln
import lightning_pb2_grpc as lnrpc


class LNDClient:
    """Low-level LND gRPC client using pure grpcio"""

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

        self._channel = None
        self._stub = None
        self._connect()

    def _connect(self):
        """Establish secure gRPC connection"""
        try:
            tls_path = os.path.expanduser(str(self.tls_cert_path))
            mac_path = os.path.expanduser(str(self.macaroon_path))

            print(f"🔑 Loading TLS cert from: {tls_path}")
            print(f"🔑 Loading macaroon from: {mac_path}")

            # Load TLS certificate
            with open(tls_path, "rb") as f:
                cert = f.read()

            # Load and encode macaroon
            with open(mac_path, "rb") as f:
                macaroon = codecs.encode(f.read(), "hex").decode()

            # Create credentials
            cert_creds = grpc.ssl_channel_credentials(cert)
            auth_creds = grpc.metadata_call_credentials(
                lambda _, callback: callback([("macaroon", macaroon)], None)
            )
            composite_creds = grpc.composite_channel_credentials(cert_creds, auth_creds)

            self._channel = grpc.secure_channel(
                f"{self.host}:{self.port}", composite_creds
            )

            self._stub = lnrpc.LightningStub(self._channel)

            print("✅ Successfully connected to LND!")

        except FileNotFoundError as e:
            raise LNDException(f"File not found: {e}. Check .env paths.")
        except Exception as e:
            raise LNDException(f"Failed to connect to LND: {str(e)}")

    # ====================== LIGHTNING METHODS ======================

    def create_invoice(
        self, memo: str, amount_sats: int, expiry_seconds: int = 3600
    ) -> Invoice:
        """Create a new Lightning invoice"""
        try:
            request = ln.Invoice(memo=memo, value=amount_sats, expiry=expiry_seconds)
            response = self._stub.AddInvoice(request)

            return Invoice(
                payment_request=response.payment_request,
                r_hash=response.r_hash.hex(),
                payment_hash=response.r_hash.hex(),
            )
        except Exception as e:
            raise LNDException(f"Failed to create invoice: {str(e)}")

    def pay_invoice(self, payment_request: str) -> PaymentResult:
        """Pay a Lightning invoice"""
        try:
            request = ln.SendRequest(payment_request=payment_request)
            response = self._stub.SendPaymentSync(request)

            success = response.status == ln.Payment.PaymentStatus.SUCCEEDED

            return PaymentResult(
                success=success,
                payment_hash=response.payment_hash.hex() if response.payment_hash else None,
                amount=response.value_sat,
                status=response.status.name,
            )
        except Exception as e:
            raise LNDException(f"Failed to pay invoice: {str(e)}")

    def send_coins(self, address: str, amount_sats: int) -> OnChainSendResult:
        """Send sats on-chain (for fee collection)"""
        try:
            request = ln.SendCoinsRequest(addr=address, amount=amount_sats, target_conf=6)
            response = self._stub.SendCoins(request)

            return OnChainSendResult(txid=response.txid, success=True)
        except Exception as e:
            raise LNDException(f"Failed to send on-chain: {str(e)}")

    def get_balance(self) -> LightningBalance:
        """Get wallet balance"""
        try:
            response = self._stub.WalletBalance(ln.WalletBalanceRequest())
            return LightningBalance(
                total_balance=str(response.total_balance),
                confirmed_balance=str(response.confirmed_balance),
                unconfirmed_balance=str(response.unconfirmed_balance),
            )
        except Exception as e:
            raise LNDException(f"Failed to get balance: {str(e)}")

    def get_channel_balance(self) -> ChannelBalance:
        """Get channel balance"""
        try:
            response = self._stub.ChannelBalance(ln.ChannelBalanceRequest())
            return ChannelBalance(
                local_balance=response.local_balance,
                remote_balance=response.remote_balance,
            )
        except Exception as e:
            raise LNDException(f"Failed to get channel balance: {str(e)}")


__all__ = ["LNDClient"]