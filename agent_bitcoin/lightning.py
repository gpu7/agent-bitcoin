import os
import subprocess
import json

from .exceptions import ConfigurationError, LNDException
from .models import (
    Invoice,
    PaymentResult,
)

# Default and only supported network for the stock Docker regtest stack.
# Mainnet requires an explicit, separate deployment decision — not a silent flag flip.
_DEFAULT_NETWORK = "regtest"


def _resolve_network() -> str:
    network = os.getenv("LND_NETWORK", _DEFAULT_NETWORK).strip().lower()
    if network == "mainnet" and os.getenv("AGENT_BITCOIN_ALLOW_MAINNET") != "1":
        raise ConfigurationError(
            "Refusing LND mainnet: set AGENT_BITCOIN_ALLOW_MAINNET=1 only for an "
            "intentional mainnet deployment (not the default regtest stack)."
        )
    if network not in ("regtest", "testnet", "mainnet", "simnet"):
        raise ConfigurationError(f"Unsupported LND_NETWORK={network!r}")
    return network


class LNDClient:
    """LND client using lncli inside Docker container (regtest by default)."""

    def __init__(self):
        self.container = (
            "agent-payment-decision-lnd"  # Default, can be overridden later
        )
        self.lnd_dir = "/home/lnd/.lnd"
        self.network = _resolve_network()

    def _run(self, *args) -> dict:
        """Run lncli with the configured network (default: regtest)."""
        cmd = [
            "docker",
            "exec",
            "-i",
            self.container,
            "lncli",
            f"--lnddir={self.lnd_dir}",
            f"--network={self.network}",
            *args,
        ]

        print(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )  # Increased default timeout

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                raise LNDException(f"lncli failed:\n{error_msg}")

            if result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"raw_output": result.stdout.strip()}
            return {}
        except subprocess.TimeoutExpired:
            raise LNDException("lncli command timed out")
        except Exception as e:
            raise LNDException(f"lncli execution failed: {str(e)}")

    def create_invoice(
        self, memo: str, amount_sats: int, expiry_seconds: int = 3600
    ) -> Invoice:
        try:
            resp = self._run(
                "addinvoice",
                f"--memo={memo}",
                f"--amt={amount_sats}",
                f"--expiry={expiry_seconds}",
            )
            return Invoice(
                payment_request=resp.get("payment_request", ""),
                r_hash=resp.get("r_hash", ""),
                payment_hash=resp.get("r_hash", ""),
            )
        except Exception as e:
            raise LNDException(f"Failed to create invoice: {str(e)}")

    def pay_invoice(
        self, payment_request: str, fee_limit_sats: int = 200
    ) -> PaymentResult:
        """Pay a Lightning invoice"""
        try:
            resp = self._run(
                "sendpayment",
                "--pay_req",
                payment_request,
                "--fee_limit",
                str(fee_limit_sats),
                "--json",
                "--force",  # Skip confirmation
            )
            # lncli sendpayment JSON varies by version: value_sat / value_msat / value
            amount = resp.get("value_sat")
            if amount is None and resp.get("value_msat") is not None:
                try:
                    amount = int(resp["value_msat"]) // 1000
                except (TypeError, ValueError):
                    amount = 0
            if amount is None and resp.get("value") is not None:
                amount = resp.get("value")
            if amount is None and resp.get("amount") is not None:
                amount = resp.get("amount")
            try:
                amount_int = int(amount) if amount is not None else 0
            except (TypeError, ValueError):
                amount_int = 0

            status = str(resp.get("status") or resp.get("payment_status") or "UNKNOWN")
            success = status.upper() in {
                "SUCCEEDED",
                "SUCCESS",
                "COMPLETE",
                "COMPLETED",
            }
            # Some older outputs omit status on success and only return payment_hash
            if (
                not success
                and resp.get("payment_hash")
                and not resp.get("payment_error")
            ):
                success = True
                if status == "UNKNOWN":
                    status = "SUCCEEDED"

            return PaymentResult(
                success=success,
                payment_hash=resp.get("payment_hash") or resp.get("payment_hash_str"),
                amount=amount_int,
                status=status,
            )
        except Exception as e:
            raise LNDException(f"Failed to pay invoice: {str(e)}")


__all__ = ["LNDClient"]
