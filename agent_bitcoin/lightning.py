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
        self.container = "agent-payment-decision-lnd"
        self.lnd_dir = "/home/lnd/.lnd"

    def _run(self, *args) -> dict:
        """Run lncli with correct regtest settings"""
        cmd = [
            "docker", "exec", "-i", self.container,
            "lncli",
            f"--lnddir={self.lnd_dir}",
            "--network=regtest",
            *args
        ]

        print(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise LNDException(f"lncli failed:\n{error_msg}")

            if result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"raw_output": result.stdout.strip()}
            return {}
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
