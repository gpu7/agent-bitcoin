"""Publish and poll signed Nostr events on NOSTR_RELAYS.

No gift wrap and no invoices. NIP-17 stays in ``nip17`` / ``examples/a2a_ln_pay.py``
because that path carries a BOLT11. This module only moves already-signed events.
"""

from __future__ import annotations

import os
import time
from typing import Any, Iterator

DEFAULT_RELAYS = "wss://relay.damus.io,wss://nos.lol"


def relay_urls() -> list[str]:
    raw = (os.environ.get("NOSTR_RELAYS") or DEFAULT_RELAYS).strip()
    return [part.strip() for part in raw.split(",") if part.strip()]


def _refuse_pytest_network() -> None:
    if os.environ.get("PYTEST_CURRENT_TEST") and (
        os.environ.get("MERCHANT_COORD_ALLOW_LIVE") != "1"
    ):
        raise SystemExit("refusing live Nostr relay during pytest")


def event_to_dict(event: Any) -> dict[str, Any]:
    kind = event.kind
    return {
        "id": event.id,
        "pubkey": event.pubkey,
        "created_at": event.created_at,
        "kind": int(kind),
        "tags": event.tags,
        "content": event.content,
        "sig": event.sig,
    }


def publish_event(
    data: dict[str, Any],
    urls: list[str] | None = None,
    *,
    timeout: float = 8,
) -> None:
    """Publish one already-signed event. Does not verify or gift-wrap."""
    _refuse_pytest_network()
    from pynostr.event import Event
    from pynostr.relay_manager import RelayManager

    chosen = relay_urls() if urls is None else list(urls)
    if not chosen:
        raise SystemExit("NOSTR_RELAYS is empty")
    ev = Event(
        content=data["content"],
        kind=int(data["kind"]),
        tags=data.get("tags") or [],
        pubkey=data.get("pubkey"),
    )
    ev.id = data.get("id")
    ev.created_at = data.get("created_at")
    ev.sig = data.get("sig")
    ev.pubkey = data.get("pubkey")
    mgr = RelayManager(timeout=timeout)
    try:
        for url in chosen:
            mgr.add_relay(url, timeout=3, close_on_eose=True)
        mgr.publish_event(ev)
        mgr.run_sync()
    finally:
        mgr.close_all_relay_connections()


def poll_events(
    urls: list[str] | None,
    *,
    kinds: list[int],
    since: int,
    timeout: float,
    limit: int = 200,
) -> Iterator[dict[str, Any]]:
    """Yield stored events until ``timeout``. Caller filters and verifies."""
    _refuse_pytest_network()
    from pynostr.filters import Filters, FiltersList
    from pynostr.relay_manager import RelayManager

    chosen = relay_urls() if urls is None else list(urls)
    if not chosen:
        raise SystemExit("NOSTR_RELAYS is empty")
    mgr = RelayManager(timeout=min(8.0, max(2.0, timeout)))
    try:
        for url in chosen:
            mgr.add_relay(url, timeout=3, close_on_eose=False)
        filt = Filters(kinds=kinds, since=since or None, limit=limit)
        mgr.add_subscription_on_all_relays("coord", FiltersList([filt]))
        deadline = time.time() + timeout
        seen: set[str] = set()
        while time.time() < deadline:
            mgr.run_sync()
            while mgr.message_pool.has_events():
                ev = mgr.message_pool.get_event().event
                eid = str(getattr(ev, "id", "") or "")
                if eid and eid in seen:
                    continue
                if eid:
                    seen.add(eid)
                yield event_to_dict(ev)
            time.sleep(0.3)
    finally:
        mgr.close_all_relay_connections()
