"""NIP-46-style remote signer (bunker JSON-RPC).

Wire: kind 24133 request/response (same kind both directions).
v1 encryption: NIP-04 via pynostr (NIP-44 preferred by the NIP; lab-safe).
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from pynostr.event import Event
from pynostr.key import PrivateKey

from agent_bitcoin.nwc.crypto import decrypt_payload, encrypt_payload
from agent_bitcoin.nwc.errors import NWCError, NWCPolicyError

NIP46_KIND = 24133
DEFAULT_ALLOWED_KINDS = frozenset({0, 1, 13, 1059, 24133})


class Nip46Bunker:
    """Holds nsec; answers connect / get_public_key / sign_event / ping / describe."""

    def __init__(
        self,
        user_sk: PrivateKey,
        *,
        allowed_kinds: frozenset[int] | None = None,
        on_request: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.user_sk = user_sk
        self.allowed_kinds = (
            allowed_kinds if allowed_kinds is not None else DEFAULT_ALLOWED_KINDS
        )
        # Connection secret keypair used on the bunker *transport* (client talks to this)
        self.conn_sk = PrivateKey()
        self.authorized_clients: set[str] = set()

    @property
    def connection_pubkey(self) -> str:
        return self.conn_sk.public_key.hex()

    @property
    def user_pubkey(self) -> str:
        return self.user_sk.public_key.hex()

    def authorize_client(self, client_pubkey: str) -> None:
        self.authorized_clients.add(client_pubkey)

    def handle_plaintext(
        self, req: dict[str, Any], *, client_pubkey: str
    ) -> dict[str, Any]:
        rid = str(req.get("id") or "")
        method = str(req.get("method") or "")
        params = req.get("params") or []
        if not isinstance(params, list):
            return _err(rid, "params must be a list")
        if self.authorized_clients and client_pubkey not in self.authorized_clients:
            return _err(rid, "unauthorized client")
        try:
            result = self._dispatch(method, params)
            return {"id": rid, "result": result, "error": None}
        except Exception as e:
            return _err(rid, str(e))

    def _dispatch(self, method: str, params: list[Any]) -> Any:
        if method in {"connect", "ping"}:
            return "ack"
        if method == "get_public_key":
            return self.user_pubkey
        if method == "describe":
            return [
                "connect",
                "ping",
                "describe",
                "get_public_key",
                "sign_event",
            ]
        if method == "sign_event":
            if not params:
                raise NWCPolicyError("sign_event needs event object")
            ev = params[0]
            if not isinstance(ev, dict):
                raise NWCPolicyError("sign_event param must be object")
            kind = int(ev.get("kind", 1))
            if kind not in self.allowed_kinds:
                raise NWCPolicyError(f"kind {kind} not allowed by bunker policy")
            signed = Event(
                kind=kind,
                content=str(ev.get("content") or ""),
                tags=list(ev.get("tags") or []),
            )
            signed.sign(self.user_sk.hex())
            return {
                "id": signed.id,
                "pubkey": signed.pubkey,
                "created_at": signed.created_at,
                "kind": signed.kind,
                "tags": signed.tags,
                "content": signed.content,
                "sig": signed.sig,
            }
        raise NWCError(f"unknown NIP-46 method {method!r}")

    def handle_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        """Decrypt kind-24133 request, return signed response event dict."""
        if int(event.get("kind", 0)) != NIP46_KIND:
            return None
        client_pubkey = str(event.get("pubkey") or "")
        clear = decrypt_payload(
            self.conn_sk.hex(), client_pubkey, event.get("content") or ""
        )
        req = json.loads(clear)
        resp_body = self.handle_plaintext(req, client_pubkey=client_pubkey)
        ct = encrypt_payload(self.conn_sk.hex(), client_pubkey, json.dumps(resp_body))
        out = Event(
            kind=NIP46_KIND,
            content=ct,
            tags=[["p", client_pubkey]],
        )
        out.sign(self.conn_sk.hex())
        return {
            "id": out.id,
            "pubkey": out.pubkey,
            "created_at": out.created_at,
            "kind": out.kind,
            "tags": out.tags,
            "content": out.content,
            "sig": out.sig,
        }


class Nip46Client:
    """Talks to a Nip46Bunker over an in-process callback (or publish/wait)."""

    def __init__(self, bunker: Nip46Bunker) -> None:
        self.bunker = bunker
        self.client_sk = PrivateKey()
        bunker.authorize_client(self.client_sk.public_key.hex())

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        req = {
            "id": uuid.uuid4().hex,
            "method": method,
            "params": list(params or []),
        }
        ev = Event(
            kind=NIP46_KIND,
            content=encrypt_payload(
                self.client_sk.hex(),
                self.bunker.connection_pubkey,
                json.dumps(req),
            ),
            tags=[["p", self.bunker.connection_pubkey]],
        )
        ev.sign(self.client_sk.hex())
        ev_dict = {
            "id": ev.id,
            "pubkey": ev.pubkey,
            "created_at": ev.created_at,
            "kind": ev.kind,
            "tags": ev.tags,
            "content": ev.content,
            "sig": ev.sig,
        }
        resp_ev = self.bunker.handle_event(ev_dict)
        if not resp_ev:
            raise NWCError("no NIP-46 response")
        clear = decrypt_payload(
            self.client_sk.hex(),
            self.bunker.connection_pubkey,
            resp_ev["content"],
        )
        body = json.loads(clear)
        if body.get("error"):
            raise NWCError(str(body["error"]))
        return body.get("result")


def _err(rid: str, message: str) -> dict[str, Any]:
    return {"id": rid, "result": None, "error": message}
