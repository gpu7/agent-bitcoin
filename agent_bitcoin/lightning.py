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
    """LND client using lncli inside Docker container"""

    def __init__(self):
        # No longer using external lncli paths
        pass

    def _run(self, *args) -> dict:
        """Run lncli inside the Docker container (most reliable method)"""
        container = "agent-payment-decision-lnd"
        
        cmd = [
            "docker", "exec", "-i", container,
            "lncli",
            "--network=regtest",
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