import os
import subprocess
import json

from .exceptions import ConfigurationError, LNDException
from .models import (
    Invoice,
    PaymentResult,
    OnChainSendResult,
    LightningBalance,
    ChannelBalance,
)

# Default network for the stock Docker regtest stack.
# Mainnet requires an explicit, separate deployment decision — not a silent flag flip.
# Signet is supported via LND_NETWORK=signet (see docs/signet.md).
_DEFAULT_NETWORK = "regtest"
_SUPPORTED_NETWORKS = frozenset({"regtest", "signet", "testnet", "mainnet", "simnet"})


def _resolve_network() -> str:
    network = os.getenv("LND_NETWORK", _DEFAULT_NETWORK).strip().lower()
    if network == "mainnet" and os.getenv("AGENT_BITCOIN_ALLOW_MAINNET") != "1":
        raise ConfigurationError(
            "Refusing LND mainnet: set AGENT_BITCOIN_ALLOW_MAINNET=1 only for an "
            "intentional mainnet deployment (not the default regtest stack)."
        )
    if network not in _SUPPORTED_NETWORKS:
        raise ConfigurationError(
            f"Unsupported LND_NETWORK={network!r}; "
            f"expected one of {sorted(_SUPPORTED_NETWORKS)}"
        )
    return network


class LNDClient:
    """LND client using lncli inside Docker container (regtest by default)."""

    def __init__(self):
        # Override with LND_CONTAINER env (e.g. agent-payment-decision-lnd-signet)
        self.container = (
            os.getenv("LND_CONTAINER", "agent-payment-decision-lnd").strip()
            or "agent-payment-decision-lnd"
        )
        self.lnd_dir = (
            os.getenv("LND_DIR", "/home/lnd/.lnd").strip() or "/home/lnd/.lnd"
        )
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
                # sendpayment often exits non-zero but prints JSON with failure_reason
                if result.stdout.strip():
                    try:
                        payload = json.loads(result.stdout)
                        if isinstance(payload, dict) and (
                            payload.get("failure_reason")
                            or payload.get("payment_error")
                            or payload.get("status")
                        ):
                            reason = (
                                payload.get("failure_reason")
                                or payload.get("payment_error")
                                or payload.get("status")
                            )
                            raise LNDException(
                                f"lncli failed: {reason}\n{result.stdout.strip()}"
                            )
                    except json.JSONDecodeError:
                        pass
                raise LNDException(f"lncli failed:\n{error_msg}")

            if result.stdout.strip():
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"raw_output": result.stdout.strip()}
            return {}
        except subprocess.TimeoutExpired:
            raise LNDException("lncli command timed out")
        except LNDException:
            raise
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

    def get_balance(self) -> LightningBalance:
        """On-chain wallet balances from lncli walletbalance."""
        try:
            resp = self._run("walletbalance")
            return LightningBalance(
                total_balance=str(resp.get("total_balance", "0")),
                confirmed_balance=str(resp.get("confirmed_balance", "0")),
                unconfirmed_balance=str(resp.get("unconfirmed_balance", "0")),
            )
        except Exception as e:
            raise LNDException(f"Failed to get wallet balance: {str(e)}") from e

    def get_channel_balance(self) -> ChannelBalance:
        """Aggregate channel local/remote balances from lncli channelbalance."""
        try:
            resp = self._run("channelbalance")
            # lncli may return nested { "sat": "..." } or flat ints/strings
            local = resp.get("local_balance", 0)
            remote = resp.get("remote_balance", 0)
            if isinstance(local, dict):
                local = local.get("sat", local.get("msat", 0))
            if isinstance(remote, dict):
                remote = remote.get("sat", remote.get("msat", 0))
            # Prefer top-level balance when local_balance missing
            if local in (0, "0", None) and resp.get("balance") is not None:
                try:
                    local = int(resp.get("balance", 0))
                except (TypeError, ValueError):
                    local = 0
            try:
                local_i = int(local) if local is not None else 0
            except (TypeError, ValueError):
                local_i = 0
            try:
                remote_i = int(remote) if remote is not None else 0
            except (TypeError, ValueError):
                remote_i = 0
            # If msat slipped through (very large), convert
            if local_i > 10**12:
                local_i //= 1000
            if remote_i > 10**12:
                remote_i //= 1000
            return ChannelBalance(local_balance=local_i, remote_balance=remote_i)
        except Exception as e:
            raise LNDException(f"Failed to get channel balance: {str(e)}") from e

    def send_coins(self, address: str, amount_sats: int) -> OnChainSendResult:
        """On-chain send (fee wallet / operator)."""
        try:
            resp = self._run(
                "sendcoins",
                f"--addr={address}",
                f"--amt={amount_sats}",
            )
            txid = resp.get("txid") or resp.get("raw_output") or ""
            return OnChainSendResult(txid=str(txid), success=bool(txid))
        except Exception as e:
            raise LNDException(f"Failed to send coins: {str(e)}") from e


__all__ = ["LNDClient"]
