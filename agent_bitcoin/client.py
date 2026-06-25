from typing import Optional, Dict, Any
import subprocess
import json
import re
from pathlib import Path

# Correct imports from models
from .models import (
    LightningConfig,
    InvoiceCreationResult,
    PaymentResult,
)
from .exceptions import (
    AgentBitcoinError,
    InvoiceCreationError,
    PaymentError,
    MacaroonError,
)


class AgentBitcoinClient:
    """
    Main SDK client for Agent-Bitcoin.
    Abstracts all docker + lncli interactions.
    """

    def __init__(self, config: Optional[LightningConfig] = None):
        self.config = config or LightningConfig.from_env()

        # Light validation for macaroons
        for name, path in [
            ("Payment Decision", self.config.macaroon_payment_decision),
            ("Bitcoin", self.config.macaroon_bitcoin),
        ]:
            if str(path).startswith("/root/") and not path.exists():
                raise MacaroonError(f"{name} macaroon not found: {path}")

    def _run_lnd_command(self, container: str, cmd: list[str]) -> Dict[str, Any]:
        """Run lncli command inside a Docker container."""
        full_cmd = [
            "docker", "exec", container, "lncli",
            "--network=regtest",
            f"--macaroonpath={self.config.macaroon_path}",
            *cmd
        ]

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                raise AgentBitcoinError(
                    f"lncli command failed: {result.stderr.strip()}"
                )

            try:
                return json.loads(result.stdout.strip())
            except (json.JSONDecodeError, TypeError):
                return {"stdout": result.stdout.strip(), "raw": True}

        except subprocess.TimeoutExpired:
            raise AgentBitcoinError("Command timed out after 60 seconds")
        except FileNotFoundError:
            raise AgentBitcoinError("docker command not found. Is Docker running?")

    def create_invoice(self, memo: str, amount_sats: int) -> InvoiceCreationResult:
        """Create a Lightning invoice on Agent-Bitcoin (payee side)."""
        if amount_sats < 1 or amount_sats > 1_000_000:
            raise InvoiceCreationError(
                f"Amount {amount_sats} sats is outside allowed range (1 - 1,000,000)"
            )

        cmd = ["addinvoice", f"--memo={memo}", f"--amt={amount_sats}"]

        response = self._run_lnd_command(self.config.container_bitcoin, cmd)

        return InvoiceCreationResult(
            payment_request=response.get("payment_request", ""),
            r_hash=response.get("r_hash"),
            add_index=response.get("add_index"),
            raw_response=response
        )

    def pay_invoice(self, payment_request: str, fee_limit_sats: int = 200) -> PaymentResult:
        """Pay a Lightning invoice from Agent-Payment-Decision (payer side)."""
        cmd = [
            "payinvoice",
            f"--pay_req={payment_request}",
            f"--fee_limit={fee_limit_sats}",
            "--force"
        ]

        response = self._run_lnd_command(
            self.config.container_payment_decision, cmd
        )

        stdout = response.get("stdout", "")

        # Robust parsing
        status_matches = re.findall(r"Payment status:\s*(SUCCEEDED|IN_FLIGHT|FAILED|UNKNOWN)", stdout)
        final_status = status_matches[-1] if status_matches else "UNKNOWN"

        amount_matches = re.findall(r"Amount \+ fee:\s*(\d+)", stdout)
        amount = int(amount_matches[-1]) if amount_matches else 0

        hash_match = re.search(r"Payment hash:\s*([a-f0-9]+)", stdout)
        preimage_match = re.search(r"preimage:\s*([a-f0-9]+)", stdout)

        success = final_status == "SUCCEEDED"

        return PaymentResult(
            success=success,
            status=final_status,
            amount=amount,
            payment_fee=0,
            payment_hash=hash_match.group(1) if hash_match else None,
            preimage=preimage_match.group(1) if preimage_match else None,
            raw_response=response
        )

    def get_balance(self, container: Optional[str] = None) -> Dict:
        """Get Lightning wallet balance."""
        target = container or self.config.container_bitcoin
        return self._run_lnd_command(target, ["walletbalance"])