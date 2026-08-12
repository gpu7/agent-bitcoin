"""Optional WebSocket NWC relay adapter (pynostr RelayManager).

Network-dependent. Prefer InMemoryNWCBus for tests and CI.

pynostr ``Relay.connect()`` stays in a read loop after the socket opens, so
``RelayManager.run_sync()`` only returns when the per-relay connect timeout
fires. Never pass the NWC RPC wait (15–30s) as ``RelayManager(timeout=…)`` —
that makes the first poll wait that long *per relay* and looks hung.

Long-lived SUB / wait-for-response must use ``close_on_eose=False``. The
default ``True`` closes the socket on empty EOSE, so a later 23195 is missed.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Sequence

from pynostr.event import Event
from pynostr.filters import Filters, FiltersList
from pynostr.relay_manager import RelayManager

from agent_bitcoin.nwc.errors import NWCError
from agent_bitcoin.nwc.policy import KIND_REQUEST, KIND_RESPONSE

# Per-relay websocket connect / one poll of run_sync. Not the NWC RPC wait.
CONNECT_TIMEOUT = 2.0
# Extra wall-clock so a hung tornado connect cannot block the caller.
PROBE_GRACE = 1.5

LogFn = Callable[[str], None]
ProbeFn = Callable[..., bool]


def register_relays(
    mgr: RelayManager,
    urls: Sequence[str],
    *,
    close_on_eose: bool,
    timeout: float = CONNECT_TIMEOUT,
    log: LogFn | None = None,
) -> list[str]:
    """Register URLs on a manager. ``add_relay`` does not open sockets."""
    added: list[str] = []
    for url in urls:
        try:
            mgr.add_relay(url, timeout=timeout, close_on_eose=close_on_eose)
            added.append(url)
            if log:
                log(f"registered {url} (close_on_eose={close_on_eose})")
        except Exception as e:
            if log:
                log(f"skip {url}: {e}")
    return added


def _default_probe_connect(url: str, timeout: float) -> None:
    mgr = RelayManager()
    try:
        mgr.add_relay(url, timeout=timeout, close_on_eose=True)
        mgr.run_sync()
    finally:
        try:
            mgr.close_all_relay_connections()
        except Exception:
            pass


def probe_relay(
    url: str,
    timeout: float = CONNECT_TIMEOUT,
    *,
    _connect: Callable[[str, float], None] | None = None,
) -> bool:
    """Try one relay in a side thread so a hung websocket cannot block."""
    connect = _connect or _default_probe_connect
    result: dict[str, bool] = {"ok": False}

    def _worker() -> None:
        try:
            connect(url, timeout)
            result["ok"] = True
        except Exception:
            result["ok"] = False

    thread = threading.Thread(target=_worker, daemon=True, name=f"nwc-probe-{url}")
    thread.start()
    thread.join(timeout + PROBE_GRACE)
    if thread.is_alive():
        return False
    return bool(result["ok"])


def select_live_relays(
    urls: Sequence[str],
    *,
    timeout: float = CONNECT_TIMEOUT,
    log: LogFn | None = None,
    probe: ProbeFn | None = None,
) -> list[str]:
    """Probe each URL; skip timeouts and errors. Never blocks past timeout+grace."""
    check = probe or probe_relay
    live: list[str] = []
    for url in urls:
        if log:
            log(f"connecting {url} …")
        try:
            ok = check(url, timeout=timeout)
        except TypeError:
            ok = check(url, timeout)
        except Exception as e:
            if log:
                log(f"skip {url}: {e}")
            continue
        if ok:
            if log:
                log(f"ok {url}")
            live.append(url)
        elif log:
            log(f"skip {url}: connect timeout or error")
    return live


def run_nwc_listen_session(
    urls: Sequence[str],
    wallet_pubkey: str,
    on_request: Callable[[dict[str, Any]], dict[str, Any] | None],
    *,
    log: LogFn | None = None,
    stop: Callable[[], bool] | None = None,
    poll_sleep: float = 0.3,
    connect_timeout: float = CONNECT_TIMEOUT,
    probe: ProbeFn | None = None,
    manager_factory: Callable[[], Any] | None = None,
) -> None:
    """Connect live relays, SUB kind 23194, poll until ``stop`` or error.

    Logs per-relay connect / skip, then ``subscribed, polling`` before the
    first ``run_sync``. Dead relays are dropped in the probe pass.

    ``run_sync`` reconnects each cycle, so the 23194 REQ is re-sent every
    poll. If ``on_request`` returns a kind-23195 dict, it is published on
    the same manager (a second RelayManager on IOLoop.current() wedges
    the listener after the first call).
    """
    live = select_live_relays(urls, timeout=connect_timeout, log=log, probe=probe)
    if not live:
        raise NWCError(f"no public relays accepted a connection: {list(urls)}")

    factory = manager_factory or RelayManager
    mgr = factory()
    added = register_relays(
        mgr,
        live,
        close_on_eose=False,
        timeout=connect_timeout,
        log=log,
    )
    if not added:
        raise NWCError("failed to register any live relay")

    flt = FiltersList(
        [
            Filters(
                kinds=[KIND_REQUEST],
                pubkey_refs=[wallet_pubkey],
                limit=20,
            )
        ]
    )
    if log:
        log(f"subscribed, polling {added}")

    seen: set[str] = set()
    while not (stop and stop()):
        # pynostr connect() opens a new websocket each run_sync; without a
        # fresh REQ the second Mac call (get_balance) is never delivered.
        mgr.add_subscription_on_all_relays(uuid.uuid4().hex, flt)
        try:
            mgr.run_sync()
        except Exception as e:
            raise NWCError(f"relay poll failed: {e}") from e
        while mgr.message_pool.has_events():
            ev = mgr.message_pool.get_event().event
            d = _event_to_dict(ev)
            if int(d.get("kind") or 0) != KIND_REQUEST:
                continue
            eid = str(d.get("id") or "")
            if eid and eid in seen:
                continue
            if eid:
                seen.add(eid)
            reply = on_request(d)
            if isinstance(reply, dict) and int(reply.get("kind") or 0) == KIND_RESPONSE:
                try:
                    mgr.publish_event(_dict_to_event(reply))
                    if log:
                        log("queued 23195 on live relays")
                except Exception as e:
                    if log:
                        log(f"failed to queue 23195: {e}")
        if poll_sleep:
            time.sleep(poll_sleep)


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
        # NWC RPC wait (publish + response). Not the websocket connect timeout.
        self.timeout = timeout

    def publish(self, event: dict[str, Any]) -> None:
        ev = _dict_to_event(event)
        # One-shot: close_on_eose is fine. Do not set RelayManager.timeout to
        # the RPC wait — that would block run_sync for the full wait per URL.
        mgr = RelayManager()
        added = register_relays(
            mgr,
            self.urls,
            close_on_eose=True,
            timeout=CONNECT_TIMEOUT,
        )
        if not added:
            raise NWCError(f"no relays accepted publish: {self.urls}")
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
        # Keep the SUB open after empty EOSE so a later 23195 is received.
        # Connect timeout stays short; `timeout` is only the RPC wait.
        mgr = RelayManager()
        added = register_relays(
            mgr,
            self.urls,
            close_on_eose=False,
            timeout=CONNECT_TIMEOUT,
        )
        if not added:
            raise NWCError(f"no relays accepted subscribe: {self.urls}")
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
