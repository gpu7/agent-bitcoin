from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
import subprocess
import json
from pathlib import Path

from .models import (
    LightningConfig,
    Invoice,
    PaymentResult,
    InvoiceCreationResult,
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
    Abstracts docker exec calls to the two LND containers.
    """

    def __init__(self, config: Optional[LightningConfig] = None):
        self.config = config or LightningConfig()

        # Verify macaroons exist
        if not self.config.macaroon_payment_decision.exists():
            raise MacaroonError(f"Macaroon not found: {self.config.macaroon_payment_decision}")
        if not self.config.macaroon_bitcoin.exists():
            raise MacaroonError(f"Macaroon not found: {self.config.macaroon_bitcoin}")

    def _run_lnd_command(self, container: str, cmd: list[str]) -> Dict[str, Any]:
        """Run a command inside an LND container."""
        full_cmd = [
            "docker", "exec", container, "lncli",
            "--network=regtest",
            f"--macaroonpath={self.config.macaroon_path}",
            *cmd
        ]
        
        try:
            result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                raise AgentBitcoinError(f"Command failed: {result.stderr.strip()}")
            
            # Try to parse JSON output
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                # Return raw stdout for commands like payinvoice that return multi-line text
                return {"stdout": result.stdout.strip(), "raw": True}
                
        except subprocess.TimeoutExpired:
            raise AgentBitcoinError("Command timed out")
        except FileNotFoundError:
            raise AgentBitcoinError("docker command not found. Is Docker running?")

    def create_invoice(self, memo: str, amount_sats: int) -> InvoiceCreationResult:
        """Create an invoice on Agent-Bitcoin (payee)."""
        if amount_sats < 1 or amount_sats > 1_000_000:
            raise InvoiceCreationError(f"Amount {amount_sats} sats is outside allowed range (1 - 1,000,000)")

        cmd = ["addinvoice", f"--memo={memo}", f"--amt={amount_sats}"]
        
        response = self._run_lnd_command(
            self.config.container_bitcoin, cmd
        )
        
        return InvoiceCreationResult(
            payment_request=response.get("payment_request"),
            r_hash=response.get("r_hash"),
            add_index=response.get("add_index"),
            raw_response=response
        )

    def pay_invoice(self, payment_request: str, fee_limit_sats: int = 200) -> PaymentResult:
        """Pay an invoice from Agent-Payment-Decision (payer)."""
        cmd = [
            "payinvoice",
            f"--pay_req={payment_request}",
            f"--fee_limit={fee_limit_sats}",
            "--force"
        ]
        
        response = self._run_lnd_command(
            self.config.container_payment_decision, cmd
        )
        
        # Parse the complex stdout from lncli payinvoice
        stdout = response.get("stdout", "")
        
        # Extract key fields
        import re
        status_match = re.search(r"Payment status:\s*(SUCCEEDED|FAILED|IN_FLIGHT)", stdout)
        amount_match = re.search(r"Amount \+ fee:\s*(\d+)", stdout)
        hash_match = re.search(r"Payment hash:\s*([a-f0-9]+)", stdout)
        preimage_match = re.search(r"preimage:\s*([a-f0-9]+)", stdout)

        success = status_match and status_match.group(1) == "SUCCEEDED"
        
        return PaymentResult(
            success=success,
            status=status_match.group(1) if status_match else "UNKNOWN",
            amount=int(amount_match.group(1)) if amount_match else 0,
            payment_hash=hash_match.group(1) if hash_match else None,
            preimage=preimage_match.group(1) if preimage_match else None,
            raw_response=response
        )

    def get_balance(self, container: str = "agent-bitcoin-lnd") -> Dict:
        """Get Lightning balance for a node."""
        return self._run_lnd_command(container, ["channelbalance"])