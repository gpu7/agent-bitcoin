"""NIP-47 NWC client (agent side) — N3.

Builds encrypted requests, publishes via a relay port (in-memory or future
WebSocket), and decrypts responses. Does not hold LND macaroons.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from pynostr.event import Event
from pynostr.key import PrivateKey

from agent_bitcoin.nwc.bus import InMemoryNWCBus
from agent_bitcoin.nwc.crypto import client_private_key, nip04_decrypt, nip04_encrypt
from agent_bitcoin.nwc.errors import NWCError, NWCPolicyError
from agent_bitcoin.nwc.policy import (
    KIND_REQUEST,
    KIND_RESPONSE,
    assert_amount_sats_allowed,
    assert_method_allowed,
    sats_to_msats,
)
from agent_bitcoin.nwc.uri import NWCConnectionURI, parse_nwc_uri


class NWCRelayPort(Protocol):
    """Minimal transport for publishing requests and receiving responses."""

    def publish(self, event: dict[str, Any]) -> None: ...

    def wait_for_response(
        self,
        *,
        request_event_id: str,
        client_pubkey: str,
        timeout: float = 5.0,
    ) -> dict[str, Any]: ...


@dataclass
class NWCCallResult:
    """Parsed successful NWC method result."""

    result_type: str
    result: dict[str, Any]


class NWCClient:
    """Agent-side NWC client bound to a connection URI + relay port."""

    def __init__(
        self,
        connection: NWCConnectionURI | str,
        *,
        relay: NWCRelayPort | None = None,
        default_timeout: float = 15.0,
        check_amounts: bool = True,
    ) -> None:
        if isinstance(connection, str):
            connection = parse_nwc_uri(connection)
        self.connection = connection
        self._sk = client_private_key(connection.secret)
        self.client_pubkey = self._sk.public_key.hex()
        self.wallet_pubkey = connection.wallet_pubkey
        self.relay: NWCRelayPort = relay if relay is not None else InMemoryNWCBus()
        self.default_timeout = default_timeout
        self.check_amounts = check_amounts

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Invoke an NWC method; return the ``result`` object or raise."""
        assert_method_allowed(method)
        params = dict(params or {})
        self._maybe_check_amount(method, params)

        payload = {"method": method, "params": params}
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        content = nip04_encrypt(self.connection.secret, self.wallet_pubkey, plaintext)

        event = Event(
            kind=KIND_REQUEST,
            content=content,
            tags=[
                ["p", self.wallet_pubkey],
                ["encryption", "nip04"],
            ],
        )
        event.sign(self.connection.secret)
        if not event.id or not event.verify():
            raise NWCError("failed to sign NWC request event")

        event_dict = _event_to_dict(event)
        self.relay.publish(event_dict)

        response = self.relay.wait_for_response(
            request_event_id=event.id,
            client_pubkey=self.client_pubkey,
            timeout=timeout if timeout is not None else self.default_timeout,
        )
        return self._parse_response(response, expected_method=method)

    def get_info(self, **kwargs: Any) -> dict[str, Any]:
        return self.call("get_info", {}, **kwargs)

    def get_balance(self, **kwargs: Any) -> dict[str, Any]:
        return self.call("get_balance", {}, **kwargs)

    def make_invoice(
        self,
        amount_sats: int,
        *,
        description: str = "",
        expiry: int = 3600,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "amount": sats_to_msats(amount_sats),
            "description": description,
            "expiry": expiry,
        }
        return self.call("make_invoice", params, **kwargs)

    def pay_invoice(
        self,
        invoice: str,
        *,
        amount_sats: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"invoice": invoice}
        if amount_sats is not None:
            params["amount"] = sats_to_msats(amount_sats)
        return self.call("pay_invoice", params, **kwargs)

    def _maybe_check_amount(self, method: str, params: dict[str, Any]) -> None:
        if not self.check_amounts:
            return
        if method == "make_invoice":
            msats = params.get("amount")
            if msats is None:
                raise NWCPolicyError("make_invoice requires amount (msats)")
            assert_amount_sats_allowed(int(msats) // 1000)
        elif method == "pay_invoice" and params.get("amount") is not None:
            assert_amount_sats_allowed(int(params["amount"]) // 1000)

    def _parse_response(
        self, response: dict[str, Any], *, expected_method: str
    ) -> dict[str, Any]:
        # Response encrypted to client by wallet; decrypt with client secret.
        ciphertext = response.get("content") or ""
        try:
            clear = nip04_decrypt(
                self.connection.secret, self.wallet_pubkey, ciphertext
            )
        except NWCError:
            raise
        except Exception as e:
            raise NWCError(f"failed to decrypt NWC response: {e}") from e

        try:
            body = json.loads(clear)
        except json.JSONDecodeError as e:
            raise NWCError(f"NWC response is not JSON: {e}") from e

        err = body.get("error")
        if err:
            code = err.get("code", "OTHER") if isinstance(err, dict) else "OTHER"
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise NWCError(f"NWC error {code}: {msg}")

        result_type = body.get("result_type") or expected_method
        result = body.get("result")
        if result is None:
            raise NWCError("NWC response missing result")
        if not isinstance(result, dict):
            raise NWCError("NWC result must be an object")
        if result_type != expected_method:
            raise NWCError(
                f"unexpected result_type {result_type!r}, expected {expected_method!r}"
            )
        return result


def _event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "pubkey": event.pubkey,
        "created_at": event.created_at,
        "kind": event.kind,
        "tags": list(event.tags or []),
        "content": event.content,
        "sig": event.sig,
    }


def sign_response_event(
    *,
    wallet_sk: PrivateKey,
    client_pubkey: str,
    request_event_id: str,
    result_type: str,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper for tests/mock wallet: build a signed kind 23195 response."""
    body: dict[str, Any] = {
        "result_type": result_type,
        "error": error,
        "result": result if error is None else None,
    }
    plaintext = json.dumps(body, separators=(",", ":"), sort_keys=True)
    content = nip04_encrypt(wallet_sk.hex(), client_pubkey, plaintext)
    event = Event(
        kind=KIND_RESPONSE,
        content=content,
        tags=[
            ["p", client_pubkey],
            ["e", request_event_id],
            ["encryption", "nip04"],
        ],
    )
    event.sign(wallet_sk.hex())
    return _event_to_dict(event)


def attach_mock_wallet(
    bus: InMemoryNWCBus,
    wallet_sk: PrivateKey,
    *,
    handlers: dict[str, Callable[..., dict[str, Any]]] | None = None,
) -> None:
    """Register a simple mock wallet on an in-memory bus (for unit tests)."""
    handlers = handlers or {}

    def _on_request(req: dict[str, Any]) -> None:
        client_pubkey = req.get("pubkey") or ""
        try:
            clear = nip04_decrypt(
                wallet_sk.hex(), client_pubkey, req.get("content") or ""
            )
            body = json.loads(clear)
        except Exception as e:
            bus.publish(
                sign_response_event(
                    wallet_sk=wallet_sk,
                    client_pubkey=client_pubkey,
                    request_event_id=req.get("id") or "",
                    result_type="unknown",
                    error={"code": "INTERNAL", "message": str(e)},
                )
            )
            return

        method = body.get("method") or "unknown"
        params = body.get("params") or {}
        try:
            assert_method_allowed(method)
            if method in handlers:
                result = handlers[method](params)
            else:
                result = _default_mock_result(method, params)
            resp = sign_response_event(
                wallet_sk=wallet_sk,
                client_pubkey=client_pubkey,
                request_event_id=req.get("id") or "",
                result_type=method,
                result=result,
            )
        except NWCPolicyError as e:
            resp = sign_response_event(
                wallet_sk=wallet_sk,
                client_pubkey=client_pubkey,
                request_event_id=req.get("id") or "",
                result_type=method,
                error={"code": e.code, "message": str(e)},
            )
        except Exception as e:
            resp = sign_response_event(
                wallet_sk=wallet_sk,
                client_pubkey=client_pubkey,
                request_event_id=req.get("id") or "",
                result_type=method,
                error={"code": "INTERNAL", "message": str(e)},
            )
        bus.publish(resp)

    bus.on_request(_on_request)


def _default_mock_result(method: str, params: dict[str, Any]) -> dict[str, Any]:
    if method == "get_info":
        return {
            "alias": "agent-bitcoin-mock-nwc",
            "network": "regtest",
            "methods": sorted(
                ["get_info", "get_balance", "make_invoice", "pay_invoice"]
            ),
        }
    if method == "get_balance":
        return {"balance": 1_000_000_000}
    if method == "make_invoice":
        amount = int(params.get("amount") or 0)
        return {
            "type": "incoming",
            "invoice": f"lnt_mock_{amount}",
            "amount": amount,
            "payment_hash": "00" * 32,
            "created_at": int(time.time()),
        }
    if method == "pay_invoice":
        return {"preimage": "11" * 32, "fees_paid": 0}
    raise NWCError(f"no mock handler for {method}")
