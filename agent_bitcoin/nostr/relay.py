"""Optional WebSocket NWC relay adapter (pynostr RelayManager).

Network-dependent. Prefer InMemoryNWCBus for tests and CI.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Sequence

from pynostr.event import Event
from pynostr.filters import Filters, FiltersList
from pynostr.relay_manager import RelayManager

from agent_bitcoin.nwc.errors import NWCError
from agent_bitcoin.nwc.policy import KIND_RESPONSE


class WebsocketNWCRelay:
    """Publish NWC events and wait for a matching kind-23195 response."""

    def __init__(
        self,
        urls: Sequence[str],
        *,
        timeout: float = 8.0,
    ) -> None:
        if not urls:
            raise NWCError("at least one relay URL is required")
        self.urls = tuple(urls)
        self.timeout = timeout

    def publish(self, event: dict[str, Any]) -> None:
        ev = _dict_to_event(event)
        mgr = RelayManager(timeout=self.timeout)
        for url in self.urls:
            mgr.add_relay(url)
        try:
            mgr.publish_event(ev)
            mgr.run_sync()
        finally:
            try:
                mgr.close_all_relay_connections()
            except Exception:
                pass

    def wait_for_response(
        self,
        *,
        request_event_id: str,
        client_pubkey: str,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        filters = FiltersList(
            [
                Filters(
                    kinds=[KIND_RESPONSE],
                    event_refs=[request_event_id],
                    limit=5,
                )
            ]
        )
        mgr = RelayManager(timeout=max(timeout, 2.0))
        for url in self.urls:
            mgr.add_relay(url)
        sub = uuid.uuid4().hex
        try:
            mgr.add_subscription_on_all_relays(sub, filters)
            deadline = time.monotonic() + max(timeout, 0.5)
            while time.monotonic() < deadline:
                mgr.run_sync()
                while mgr.message_pool.has_events():
                    msg = mgr.message_pool.get_event()
                    ev = msg.event
                    d = _event_to_dict(ev)
                    if int(d.get("kind", 0)) != KIND_RESPONSE:
                        continue
                    if _tag_has(d, "e", request_event_id) and _tag_has(
                        d, "p", client_pubkey
                    ):
                        return d
                time.sleep(0.2)
        finally:
            try:
                mgr.close_all_relay_connections()
            except Exception:
                pass
        raise NWCError(f"timeout waiting for NWC response on relays {self.urls}")


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


def _dict_to_event(d: dict[str, Any]) -> Event:
    ev = Event(
        kind=int(d.get("kind") or 1),
        content=str(d.get("content") or ""),
        tags=list(d.get("tags") or []),
    )
    if d.get("pubkey"):
        ev.pubkey = d["pubkey"]
    if d.get("id"):
        ev.id = d["id"]
    if d.get("sig"):
        ev.sig = d["sig"]
    if d.get("created_at"):
        ev.created_at = int(d["created_at"])
    return ev


def _tag_has(event: dict[str, Any], name: str, value: str) -> bool:
    for tag in event.get("tags") or []:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2:
            if tag[0] == name and tag[1] == value:
                return True
    return False
