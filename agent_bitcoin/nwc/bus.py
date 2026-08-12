"""In-process NWC event bus for lab/mock relays (no WebSocket)."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from agent_bitcoin.nwc.errors import NWCError
from agent_bitcoin.nwc.policy import KIND_REQUEST, KIND_RESPONSE

EventDict = dict[str, Any]
RequestHandler = Callable[[EventDict], None]


class InMemoryNWCBus:
    """Shared memory bus: client publishes requests; wallet handler replies.

    Used for offline tests and local single-process regtest smoke before
    real relays land.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[EventDict] = []
        self._request_handlers: list[RequestHandler] = []
        self._cv = threading.Condition(self._lock)

    def on_request(self, handler: RequestHandler) -> None:
        """Register a wallet-side handler for kind 23194 events."""
        with self._lock:
            self._request_handlers.append(handler)

    def publish(self, event: EventDict) -> None:
        kind = int(event.get("kind", 0))
        with self._cv:
            self._events.append(dict(event))
            self._cv.notify_all()
            handlers = list(self._request_handlers)
        if kind == KIND_REQUEST:
            for h in handlers:
                h(dict(event))

    def wait_for_response(
        self,
        *,
        request_event_id: str,
        client_pubkey: str,
        timeout: float = 5.0,
    ) -> EventDict:
        """Block until a kind 23195 response for ``request_event_id`` appears."""
        deadline = time.monotonic() + max(timeout, 0.1)
        with self._cv:
            while True:
                for ev in self._events:
                    if int(ev.get("kind", 0)) != KIND_RESPONSE:
                        continue
                    if not _tag_has(ev, "e", request_event_id):
                        continue
                    if not _tag_has(ev, "p", client_pubkey):
                        continue
                    return dict(ev)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise NWCError(
                        f"timeout waiting for NWC response to {request_event_id[:16]}…"
                    )
                self._cv.wait(timeout=remaining)

    def all_events(self) -> list[EventDict]:
        with self._lock:
            return [dict(e) for e in self._events]


def _tag_has(event: EventDict, tag_name: str, value: str) -> bool:
    for tag in event.get("tags") or []:
        if (
            isinstance(tag, (list, tuple))
            and len(tag) >= 2
            and tag[0] == tag_name
            and tag[1] == value
        ):
            return True
    return False
