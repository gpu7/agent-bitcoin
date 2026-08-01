"""LND access: Docker lncli (lab default) or gRPC + macaroon (production path)."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

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
_DEFAULT_TRANSPORT = "docker"
_SUPPORTED_TRANSPORTS = frozenset({"docker", "grpc"})


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


def _resolve_transport() -> str:
    transport = (
        os.getenv("LND_TRANSPORT", _DEFAULT_TRANSPORT).strip().lower()
        or _DEFAULT_TRANSPORT
    )
    if transport not in _SUPPORTED_TRANSPORTS:
        raise ConfigurationError(
            f"Unsupported LND_TRANSPORT={transport!r}; "
            f"expected one of {sorted(_SUPPORTED_TRANSPORTS)}"
        )
    return transport


def _bytes_to_hex(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, str):
        return value
    return str(value)


def _payment_result_from_lncli_dict(resp: dict) -> PaymentResult:
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
    if not success and resp.get("payment_hash") and not resp.get("payment_error"):
        success = True
        if status == "UNKNOWN":
            status = "SUCCEEDED"

    return PaymentResult(
        success=success,
        payment_hash=resp.get("payment_hash") or resp.get("payment_hash_str"),
        amount=amount_int,
        status=status,
    )


def _channel_balance_from_dict(resp: dict) -> ChannelBalance:
    local = resp.get("local_balance", 0)
    remote = resp.get("remote_balance", 0)
    if isinstance(local, dict):
        local = local.get("sat", local.get("msat", 0))
    if isinstance(remote, dict):
        remote = remote.get("sat", remote.get("msat", 0))
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
    if local_i > 10**12:
        local_i //= 1000
    if remote_i > 10**12:
        remote_i //= 1000
    return ChannelBalance(local_balance=local_i, remote_balance=remote_i)


class DockerLNDClient:
    """LND via `docker exec … lncli` (lab default)."""

    transport = "docker"

    def __init__(self) -> None:
        self.container = (
            os.getenv("LND_CONTAINER", "agent-payment-decision-lnd").strip()
            or "agent-payment-decision-lnd"
        )
        self.lnd_dir = (
            os.getenv("LND_DIR", "/home/lnd/.lnd").strip() or "/home/lnd/.lnd"
        )
        self.network = _resolve_network()

    def _run(self, *args: str) -> dict:
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
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
        except subprocess.TimeoutExpired as e:
            raise LNDException("lncli command timed out") from e
        except LNDException:
            raise
        except Exception as e:
            raise LNDException(f"lncli execution failed: {str(e)}") from e

    def get_info(self) -> dict:
        return self._run("getinfo")

    def list_channels(self) -> dict:
        return self._run("listchannels")

    def decode_pay_req(self, payment_request: str) -> dict:
        return self._run("decodepayreq", payment_request)

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
            raise LNDException(f"Failed to create invoice: {str(e)}") from e

    def pay_invoice(
        self, payment_request: str, fee_limit_sats: int = 200
    ) -> PaymentResult:
        try:
            resp = self._run(
                "sendpayment",
                "--pay_req",
                payment_request,
                "--fee_limit",
                str(fee_limit_sats),
                "--json",
                "--force",
            )
            return _payment_result_from_lncli_dict(resp)
        except Exception as e:
            raise LNDException(f"Failed to pay invoice: {str(e)}") from e

    def get_balance(self) -> LightningBalance:
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
        try:
            resp = self._run("channelbalance")
            return _channel_balance_from_dict(resp)
        except Exception as e:
            raise LNDException(f"Failed to get channel balance: {str(e)}") from e

    def send_coins(self, address: str, amount_sats: int) -> OnChainSendResult:
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


class GrpcLNDClient:
    """LND via gRPC + TLS cert + macaroon (production-oriented path)."""

    transport = "grpc"

    def __init__(self) -> None:
        self.network = _resolve_network()
        host = os.getenv("LND_GRPC_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = os.getenv("LND_GRPC_PORT", "10009").strip() or "10009"
        self.ip_address = f"{host}:{port}"
        self.cert_filepath = (
            os.getenv("LND_TLS_CERT_PATH") or os.getenv("LND_CERT_PATH") or ""
        ).strip()
        self.macaroon_filepath = (os.getenv("LND_MACAROON_PATH") or "").strip()
        if not self.cert_filepath or not self.macaroon_filepath:
            raise ConfigurationError(
                "LND_TRANSPORT=grpc requires LND_TLS_CERT_PATH and LND_MACAROON_PATH "
                "(see docs/lnd-client.md)."
            )
        if not os.path.isfile(self.cert_filepath):
            raise ConfigurationError(f"LND TLS cert not found: {self.cert_filepath}")
        if not os.path.isfile(self.macaroon_filepath):
            raise ConfigurationError(
                f"LND macaroon not found: {self.macaroon_filepath}"
            )
        try:
            from lndgrpc import LNDClient as RawLNDClient
        except ImportError as e:
            raise ConfigurationError(
                "lnd-grpc-client is required for LND_TRANSPORT=grpc"
            ) from e
        try:
            self._raw = RawLNDClient(
                ip_address=self.ip_address,
                cert_filepath=self.cert_filepath,
                macaroon_filepath=self.macaroon_filepath,
            )
        except Exception as e:
            raise LNDException(
                f"Failed to connect LND gRPC at {self.ip_address}: {e}"
            ) from e

    def _msg_to_dict(self, msg: Any) -> dict:
        try:
            from google.protobuf.json_format import MessageToDict

            return MessageToDict(msg, preserving_proto_field_name=True)
        except Exception:
            # Best-effort fallback
            return {"raw": str(msg)}

    def get_info(self) -> dict:
        try:
            return self._msg_to_dict(self._raw.get_info())
        except Exception as e:
            raise LNDException(f"get_info failed: {e}") from e

    def list_channels(self) -> dict:
        try:
            return self._msg_to_dict(self._raw.list_channels())
        except Exception as e:
            raise LNDException(f"list_channels failed: {e}") from e

    def decode_pay_req(self, payment_request: str) -> dict:
        try:
            return self._msg_to_dict(self._raw.decode_pay_req(payment_request))
        except Exception as e:
            raise LNDException(f"decode_pay_req failed: {e}") from e

    def create_invoice(
        self, memo: str, amount_sats: int, expiry_seconds: int = 3600
    ) -> Invoice:
        try:
            resp = self._raw.add_invoice(
                value=int(amount_sats),
                memo=memo or "",
                expiry=int(expiry_seconds),
            )
            payment_request = getattr(resp, "payment_request", "") or ""
            r_hash = _bytes_to_hex(getattr(resp, "r_hash", b""))
            return Invoice(
                payment_request=payment_request,
                r_hash=r_hash,
                payment_hash=r_hash,
            )
        except LNDException:
            raise
        except Exception as e:
            raise LNDException(f"Failed to create invoice: {e}") from e

    def pay_invoice(
        self, payment_request: str, fee_limit_sats: int = 200
    ) -> PaymentResult:
        try:
            fee_limit_msat = int(fee_limit_sats) * 1000
            resp = self._raw.send_payment(
                payment_request=payment_request,
                fee_limit_msat=fee_limit_msat,
            )
            d = self._msg_to_dict(resp)
            # SendResponse: payment_error, payment_preimage, payment_hash, payment_route
            err = getattr(resp, "payment_error", None) or d.get("payment_error") or ""
            if err:
                raise LNDException(f"send_payment failed: {err}")
            payment_hash = _bytes_to_hex(
                getattr(resp, "payment_hash", None) or d.get("payment_hash")
            )
            # Prefer route total for amount when present
            amount_int = 0
            route = getattr(resp, "payment_route", None)
            if route is not None:
                total = getattr(route, "total_amt", None)
                if total is not None:
                    try:
                        amount_int = int(total)
                    except (TypeError, ValueError):
                        amount_int = 0
            if amount_int == 0 and d.get("payment_route"):
                try:
                    amount_int = int(d["payment_route"].get("total_amt", 0))
                except (TypeError, ValueError, AttributeError):
                    amount_int = 0
            return PaymentResult(
                success=bool(payment_hash) and not err,
                payment_hash=payment_hash or None,
                amount=amount_int,
                status="SUCCEEDED" if payment_hash and not err else "FAILED",
            )
        except LNDException:
            raise
        except Exception as e:
            raise LNDException(f"Failed to pay invoice: {e}") from e

    def get_balance(self) -> LightningBalance:
        try:
            resp = self._raw.wallet_balance()
            d = self._msg_to_dict(resp)
            return LightningBalance(
                total_balance=str(d.get("total_balance", "0")),
                confirmed_balance=str(d.get("confirmed_balance", "0")),
                unconfirmed_balance=str(d.get("unconfirmed_balance", "0")),
            )
        except Exception as e:
            raise LNDException(f"Failed to get wallet balance: {e}") from e

    def get_channel_balance(self) -> ChannelBalance:
        try:
            resp = self._raw.channel_balance()
            d = self._msg_to_dict(resp)
            return _channel_balance_from_dict(d)
        except Exception as e:
            raise LNDException(f"Failed to get channel balance: {e}") from e

    def send_coins(self, address: str, amount_sats: int) -> OnChainSendResult:
        try:
            resp = self._raw.send_coins(address=address, amount=int(amount_sats))
            txid = getattr(resp, "txid", None) or self._msg_to_dict(resp).get(
                "txid", ""
            )
            return OnChainSendResult(txid=str(txid), success=bool(txid))
        except Exception as e:
            raise LNDException(f"Failed to send coins: {e}") from e

    def _run(self, *args: str) -> dict:
        """Limited lncli-style adapter for callers that still use _run."""
        if not args:
            raise LNDException("grpc _run requires a command")
        cmd = args[0]
        if cmd == "getinfo":
            return self.get_info()
        if cmd == "listchannels":
            return self.list_channels()
        if cmd == "channelbalance":
            bal = self.get_channel_balance()
            return {
                "balance": str(bal.local_balance),
                "local_balance": {"sat": str(bal.local_balance)},
                "remote_balance": {"sat": str(bal.remote_balance)},
            }
        if cmd == "walletbalance":
            b = self.get_balance()
            return {
                "total_balance": b.total_balance,
                "confirmed_balance": b.confirmed_balance,
                "unconfirmed_balance": b.unconfirmed_balance,
            }
        if cmd == "decodepayreq" and len(args) >= 2:
            return self.decode_pay_req(args[1])
        raise LNDException(
            f"grpc transport does not support _run({cmd!r}); "
            "use create_invoice/pay_invoice/get_* methods or LND_TRANSPORT=docker"
        )


def create_lnd_client() -> DockerLNDClient | GrpcLNDClient:
    """Return docker or grpc LND client from LND_TRANSPORT (default: docker)."""
    transport = _resolve_transport()
    if transport == "grpc":
        return GrpcLNDClient()
    return DockerLNDClient()


class LNDClient:
    """
    Backward-compatible constructor: LNDClient() returns DockerLNDClient or GrpcLNDClient.

    Prefer create_lnd_client() in new code. Default transport remains docker (lab).
    """

    def __new__(cls, *args: Any, **kwargs: Any):
        if cls is not LNDClient:
            return super().__new__(cls)
        return create_lnd_client()


__all__ = [
    "LNDClient",
    "DockerLNDClient",
    "GrpcLNDClient",
    "create_lnd_client",
    "_resolve_network",
    "_resolve_transport",
]
