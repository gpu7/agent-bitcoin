import os
import subprocess
import json
from typing import Optional

from .exceptions import LNDException
from .models import (
    Invoice,
    PaymentResult,
    OnChainSendResult,
    LightningBalance,
    ChannelBalance,
)


class LNDClient:
    """LND client using lncli with explicit everything"""

    def __init__(self):
        self.lncli = "/Users/richardcasey/go/bin/lncli"
        
        self.tls_cert = "/Users/richardcasey/Library/Application Support/Lnd/tls.cert"
        self.macaroon = "/tmp/agent-payment-decision.macaroon"
        
        self.network = "--network=regtest"

    def _run(self, *args) -> dict:
        """Run lncli with very explicit flags"""
        cmd = [
            self.lncli,
            self.network,
            f"--tlscertpath={self.tls_cert}",
            f"--macaroonpath={self.macaroon}",
            "--rpcserver=localhost:10009",
            "--insecure",
            "--no-macaroons",
            *args
        ]
        
        print(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise LNDException(f"lncli failed:\n{error_msg}")
            
            return json.loads(result.stdout) if result.stdout.strip() else {}
        except Exception as e:
            raise LNDException(f"lncli execution failed: {str(e)}")

    def create_invoice(self, memo: str, amount_sats: int, expiry_seconds: int = 3600) -> Invoice:
        try:
            resp = self._run(
                "addinvoice",
                f"--memo={memo}",
                f"--amt={amount_sats}",
                f"--expiry={expiry_seconds}"
            )
            return Invoice(
                payment_request=resp.get("payment_request", ""),
                r_hash=resp.get("r_hash", ""),
                payment_hash=resp.get("r_hash", ""),
            )
        except Exception as e:
            raise LNDException(f"Failed to create invoice: {str(e)}")


__all__ = ["LNDClient"]