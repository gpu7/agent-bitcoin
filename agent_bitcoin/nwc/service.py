"""NIP-47 NWC wallet service (operator side) — N4.

Listens for encrypted requests on an in-memory bus (lab) or future WebSocket
relays, enforces method/budget policy, and executes Lightning ops via LND.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pynostr.key import PrivateKey

from agent_bitcoin.nwc.bus import InMemoryNWCBus
from agent_bitcoin.nwc.client import sign_response_event
from agent_bitcoin.nwc.crypto import client_private_key, nip04_decrypt
from agent_bitcoin.nwc.errors import NWCError, NWCPolicyError
from agent_bitcoin.nwc.policy import (
    V1_ALLOWED_METHODS,
    NWCBudgetPolicy,
    assert_amount_sats_allowed,
    assert_method_allowed,
    msats_to_sats,
    nwc_enabled,
    sats_to_msats,
)
from agent_bitcoin.nwc.uri import build_nwc_uri


@runtime_checkable
class NWCLightningBackend(Protocol):
    """Minimal LND surface used by the NWC service."""

    def get_info(self) -> dict: ...

    def get_channel_balance(self) -> Any: ...

    def get_balance(self) -> Any: ...

    def create_invoice(
        self, memo: str, amount_sats: int, expiry_seconds: int = 3600
    ) -> Any: ...

    def pay_invoice(self, payment_request: str, fee_limit_sats: int = 200) -> Any: ...

    def decode_pay_req(self, payment_request: str) -> dict: ...


@dataclass
class NWCService:
    """Operator wallet service: authorize clients + execute LND methods."""

    wallet_sk: PrivateKey
    lnd: NWCLightningBackend
    bus: InMemoryNWCBus
    budget: NWCBudgetPolicy = field(default_factory=NWCBudgetPolicy.from_env)
    require_enable: bool = True
    require_client_auth: bool = True
    fee_limit_sats: int = 200
    authorized_client_pubkeys: set[str] = field(default_factory=set)
    _attached: bool = field(default=False, init=False, repr=False)

    @property
    def wallet_pubkey(self) -> str:
        return self.wallet_sk.public_key.hex()

    def authorize_client_secret(self, secret_hex: str) -> str:
        """Authorize a client secret; return client pubkey hex."""
        pk = client_private_key(secret_hex).public_key.hex()
        self.authorized_client_pubkeys.add(pk)
        return pk

    def issue_connection(
        self,
        *,
        relays: list[str] | None = None,
        lud16: str | None = None,
    ) -> str:
        """Create a new client secret, authorize it, return NWC URI."""
        secret = secrets.token_hex(32)
        self.authorize_client_secret(secret)
        relay_list = relays or ["wss://relay.local.invalid"]
        return build_nwc_uri(
            self.wallet_pubkey,
            secret=secret,
            relays=relay_list,
            lud16=lud16,
        )

    def attach(self) -> None:
        """Register request handler on the bus (idempotent)."""
        if self._attached:
            return
        self.bus.on_request(self.handle_request_event)
        self._attached = True

    def handle_request_event(self, req: dict[str, Any]) -> None:
        """Process one kind-23194 request event and publish a response."""
        client_pubkey = str(req.get("pubkey") or "")
        request_id = str(req.get("id") or "")
        method = "unknown"
        try:
            if self.require_enable and not nwc_enabled():
                raise NWCPolicyError(
                    "NWC disabled: set AGENT_BITCOIN_NWC_ENABLE=1",
                    code="RESTRICTED",
                )
            if self.require_client_auth and (
                client_pubkey not in self.authorized_client_pubkeys
            ):
                raise NWCPolicyError(
                    "client pubkey is not authorized for this wallet",
                    code="UNAUTHORIZED",
                )

            clear = nip04_decrypt(
                self.wallet_sk.hex(), client_pubkey, req.get("content") or ""
            )
            body = json.loads(clear)
            method = str(body.get("method") or "unknown")
            params = body.get("params") or {}
            if not isinstance(params, dict):
                raise NWCError("params must be an object")

            assert_method_allowed(method)
            result = self._dispatch(method, params)
            self.bus.publish(
                sign_response_event(
                    wallet_sk=self.wallet_sk,
                    client_pubkey=client_pubkey,
                    request_event_id=request_id,
                    result_type=method,
                    result=result,
                )
            )
        except NWCPolicyError as e:
            self.bus.publish(
                sign_response_event(
                    wallet_sk=self.wallet_sk,
                    client_pubkey=client_pubkey,
                    request_event_id=request_id,
                    result_type=method,
                    error={"code": e.code, "message": str(e)},
                )
            )
        except Exception as e:
            code = "INTERNAL"
            msg = str(e)
            low = msg.lower()
            if "insufficient" in low or "balance" in low:
                code = "INSUFFICIENT_BALANCE"
            elif "route" in low or "payment failed" in low or "failed to pay" in low:
                code = "PAYMENT_FAILED"
            self.bus.publish(
                sign_response_event(
                    wallet_sk=self.wallet_sk,
                    client_pubkey=client_pubkey,
                    request_event_id=request_id,
                    result_type=method,
                    error={"code": code, "message": msg},
                )
            )

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "get_info":
            return self._get_info()
        if method == "get_balance":
            return self._get_balance()
        if method == "make_invoice":
            return self._make_invoice(params)
        if method == "pay_invoice":
            return self._pay_invoice(params)
        raise NWCPolicyError(
            f"method {method!r} not implemented", code="NOT_IMPLEMENTED"
        )

    def _get_info(self) -> dict[str, Any]:
        info = self.lnd.get_info() or {}
        network = "regtest"
        chains = info.get("chains") or []
        if chains and isinstance(chains[0], dict):
            network = str(chains[0].get("network") or network)
        return {
            "alias": str(info.get("alias") or "agent-bitcoin-nwc"),
            "color": str(info.get("color") or ""),
            "pubkey": str(info.get("identity_pubkey") or ""),
            "network": network,
            "block_height": int(info.get("block_height") or 0),
            "block_hash": str(info.get("block_hash") or ""),
            "methods": sorted(V1_ALLOWED_METHODS),
        }

    def _get_balance(self) -> dict[str, Any]:
        # Spendable LN local balance (msats) + confirmed on-chain (msats).
        try:
            ch = self.lnd.get_channel_balance()
            local = int(getattr(ch, "local_balance", 0) or 0)
        except Exception:
            local = 0
        try:
            w = self.lnd.get_balance()
            onchain = int(getattr(w, "confirmed_balance", 0) or 0)
        except Exception:
            onchain = 0
        return {"balance": sats_to_msats(local + onchain)}

    def _make_invoice(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("amount") is None:
            raise NWCPolicyError("make_invoice requires amount (msats)")
        amount_sats = msats_to_sats(int(params["amount"]))
        assert_amount_sats_allowed(
            amount_sats, policy=self.budget, require_enable=False
        )
        memo = str(params.get("description") or "nwc-invoice")
        expiry = int(params.get("expiry") or 3600)
        inv = self.lnd.create_invoice(
            memo=memo, amount_sats=amount_sats, expiry_seconds=expiry
        )
        payment_request = getattr(inv, "payment_request", None) or ""
        payment_hash = (
            getattr(inv, "payment_hash", None) or getattr(inv, "r_hash", None) or ""
        )
        return {
            "type": "incoming",
            "invoice": payment_request,
            "description": memo,
            "payment_hash": str(payment_hash),
            "amount": sats_to_msats(amount_sats),
            "fees_paid": 0,
            "created_at": int(time.time()),
            "expires_at": int(time.time()) + expiry,
        }

    def _pay_invoice(self, params: dict[str, Any]) -> dict[str, Any]:
        invoice = str(params.get("invoice") or "")
        if not invoice:
            raise NWCPolicyError("pay_invoice requires invoice", code="OTHER")

        amount_sats: int | None = None
        if params.get("amount") is not None:
            amount_sats = msats_to_sats(int(params["amount"]))
        else:
            try:
                decoded = self.lnd.decode_pay_req(invoice)
                if decoded.get("num_satoshis") is not None:
                    amount_sats = int(decoded["num_satoshis"])
                elif decoded.get("num_msat") is not None:
                    amount_sats = msats_to_sats(int(decoded["num_msat"]))
            except Exception as e:
                raise NWCError(f"failed to decode invoice: {e}") from e

        if amount_sats is None:
            raise NWCPolicyError(
                "could not determine invoice amount for budget check",
                code="OTHER",
            )
        assert_amount_sats_allowed(
            amount_sats, policy=self.budget, require_enable=False
        )

        result = self.lnd.pay_invoice(invoice, fee_limit_sats=self.fee_limit_sats)
        success = bool(getattr(result, "success", False))
        status = str(getattr(result, "status", "") or "")
        if not success and status.upper() not in {"SUCCEEDED", "SUCCESS", "COMPLETE"}:
            raise NWCError(
                f"payment failed: status={status!r}",
            )
        payment_hash = getattr(result, "payment_hash", None) or ""
        # LND lncli rarely returns preimage in our PaymentResult model; use hash.
        preimage = payment_hash if payment_hash else "0" * 64
        return {
            "preimage": str(preimage),
            "fees_paid": 0,
        }


def create_nwc_service(
    *,
    lnd: NWCLightningBackend | None = None,
    bus: InMemoryNWCBus | None = None,
    wallet_sk: PrivateKey | None = None,
    require_enable: bool = True,
) -> NWCService:
    """Factory: optional LNDClient from env when ``lnd`` is None."""
    if lnd is None:
        from agent_bitcoin.lightning import LNDClient

        lnd = LNDClient()
    svc = NWCService(
        wallet_sk=wallet_sk or PrivateKey(),
        lnd=lnd,
        bus=bus or InMemoryNWCBus(),
        require_enable=require_enable,
    )
    svc.attach()
    return svc
