"""Merchant-demo coordination: signed Nostr events, not a file bus.

Kind **8139** is a regular kind (NIP-01 range 1000–9999). Relays keep every
event. It is not kind 1, and it is not addressable, so a later concede does
not replace an earlier negotiate from the same key.

Payloads are npub, score, vote, and invoice id. They are not NIP-17 gift
wraps. BOLT11, preimage, nsec, and macaroon are refused. A2A invoices stay
on NIP-17 in ``examples/a2a_ln_pay.py``. L402 HTTP is a separate hop.

Live: ``NOSTR_RELAYS`` (default damus + nos.lol). ``--offline-bus`` spawns a
localhost mock (127.0.0.1, ``MERCHANT_MOCK_PORT``, default 8765) so two
terminals do not share a message directory. Every accepted event must verify
(id, sig, pubkey) and the signer must match the claimed role.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from agent_bitcoin.nostr.ws_relay import event_to_dict, poll_events, publish_event

# Regular custom kind. Not in the NIP kind table (checked 2026-09). Not kind 1.
KIND_MERCHANT = 8139
COORD_TAG = "agent-bitcoin-merchant-v1"
DEFAULT_RELAYS = "wss://relay.damus.io,wss://nos.lol"
MOCK_HOST = "127.0.0.1"
_SECRET_KEYS = frozenset({"bolt11", "preimage", "nsec", "macaroon", "payment_request"})
_ANNOUNCED: set[int] = set()
_LOCK = threading.Lock()


def mock_port() -> int:
    raw = (os.environ.get("MERCHANT_MOCK_PORT") or "8765").strip()
    return int(raw)


def mock_idle_s() -> float:
    raw = (os.environ.get("MERCHANT_MOCK_IDLE") or "60").strip()
    return float(raw)


def _tag(data: dict[str, Any], name: str) -> str:
    for item in data.get("tags") or []:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and item[0] == name:
            return str(item[1])
    return ""


def _npub_hex(npub: str) -> str | None:
    try:
        from bech32 import bech32_decode, convertbits
    except ImportError:
        return None
    hrp, data = bech32_decode((npub or "").strip())
    if hrp != "npub" or not data:
        return None
    raw = bytes(convertbits(data, 5, 8, False) or b"")
    if len(raw) != 32:
        return None
    return raw.hex()


def role_pubkey_hex(key_dir: Path, role: str) -> str | None:
    path = Path(key_dir) / f"{role}.pub.json"
    if not path.is_file():
        return None
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    hx = str(body.get("pubkey_hex") or "").strip().lower()
    return hx or None


def _leaks(body: Any) -> bool:
    if not isinstance(body, dict):
        return False
    for key, value in body.items():
        if str(key) in _SECRET_KEYS:
            return True
        if isinstance(value, str):
            low = value.strip().lower()
            if low.startswith("nsec1") or low.startswith("lnbc"):
                return True
        elif isinstance(value, dict) and _leaks(value):
            return True
    return False


def _signature_ok(data: dict[str, Any]) -> bool:
    """True only when the wire id matches the canonical id and the sig verifies."""
    try:
        from pynostr.event import Event

        claimed = str(data.get("id") or "")
        sig = str(data.get("sig") or "")
        pubkey = str(data.get("pubkey") or "")
        if not claimed or not sig or len(pubkey) != 64:
            return False
        ev = Event(
            content=str(data.get("content") if data.get("content") is not None else ""),
            pubkey=pubkey,
            created_at=int(data.get("created_at") or 0),
            kind=int(data.get("kind")),
            tags=list(data.get("tags") or []),
            sig=sig,
        )
        if str(ev.id) != claimed:
            return False
        return bool(ev.verify())
    except Exception:
        return False


def accept(
    data: dict[str, Any],
    invoice_id: str,
    *,
    key_dir: Path | None,
    round_n: int | None,
) -> bool:
    """Reject bad id/sig, wrong kind, wrong invoice, secrets, or a mismatched role."""
    try:
        if int(data.get("kind", 0)) != KIND_MERCHANT:
            return False
        if _tag(data, "t") != COORD_TAG:
            return False
        body = json.loads(data.get("content") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(body, dict) or _leaks(body):
        return False
    if int(body.get("v") or 0) != 1:
        return False
    if str(body.get("invoice_id") or "") != str(invoice_id):
        return False
    if round_n is not None:
        try:
            if int(body.get("round")) != int(round_n):
                return False
        except (TypeError, ValueError):
            return False
    if not _signature_ok(data):
        return False
    pubkey = str(data.get("pubkey") or "").lower()
    for field in ("npub", "payer_npub", "loser_npub"):
        claimed = body.get(field)
        if not claimed:
            continue
        hx = _npub_hex(str(claimed))
        if hx != pubkey:
            return False
    if key_dir is not None:
        role = _tag(data, "role")
        if not role:
            return False
        expected = role_pubkey_hex(Path(key_dir), role)
        if not expected or expected != pubkey:
            return False
    return True


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.cv = threading.Condition()

    def add(self, ev: dict[str, Any]) -> None:
        stored = json.loads(json.dumps(ev))
        with self.cv:
            self.events.append(stored)
            if len(self.events) > 2000:
                del self.events[:1000]
            self.cv.notify_all()


class _ServerState:
    def __init__(self) -> None:
        self.hub = _Hub()
        self.clients = 0
        self.lock = threading.Lock()


def _send(conn: socket.socket, payload: dict[str, Any]) -> None:
    blob = (json.dumps(payload, separators=(",", ":")) + "\n").encode()
    conn.sendall(blob)


def _handle(conn: socket.socket, state: _ServerState) -> None:
    with state.lock:
        state.clients += 1
    buf = b""
    watching = False
    sent = 0
    conn.settimeout(0.4)
    try:
        while True:
            if watching:
                with state.hub.cv:
                    fresh = state.hub.events[sent:]
                    sent = len(state.hub.events)
                    if not fresh:
                        state.hub.cv.wait(timeout=0.2)
                        fresh = state.hub.events[sent:]
                        sent = len(state.hub.events)
                for ev in fresh:
                    _send(conn, {"op": "event", "event": ev})
            try:
                chunk = conn.recv(65536)
            except TimeoutError:
                continue
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode())
                except json.JSONDecodeError:
                    continue
                op = msg.get("op")
                if op == "pub" and isinstance(msg.get("event"), dict):
                    state.hub.add(msg["event"])
                    _send(conn, {"op": "ok"})
                elif op == "watch":
                    watching = True
                    with state.hub.cv:
                        backlog = list(state.hub.events)
                        sent = len(backlog)
                    for ev in backlog:
                        _send(conn, {"op": "event", "event": ev})
                elif op == "hold":
                    _send(conn, {"op": "ok"})
                    while True:
                        try:
                            parked = conn.recv(65536)
                        except TimeoutError:
                            continue
                        if not parked:
                            break
                    break
                else:
                    _send(conn, {"op": "err"})
    except (OSError, TypeError, ValueError):
        pass
    finally:
        with state.lock:
            state.clients -= 1
        try:
            conn.close()
        except OSError:
            pass


def serve_forever(port: int) -> None:
    """Block as the mock relay. Exit after idle seconds with zero clients."""
    state = _ServerState()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((MOCK_HOST, int(port)))
    except OSError:
        return
    sock.listen(64)
    sock.settimeout(0.5)
    idle_s = mock_idle_s()

    def _idle() -> None:
        quiet = 0.0
        while True:
            time.sleep(0.25)
            with state.lock:
                clients = state.clients
            if clients == 0:
                quiet += 0.25
                if quiet >= idle_s:
                    os._exit(0)
            else:
                quiet = 0.0

    threading.Thread(target=_idle, name="merchant-mock-idle", daemon=True).start()
    while True:
        try:
            conn, _addr = sock.accept()
        except TimeoutError:
            continue
        except OSError:
            return
        threading.Thread(
            target=_handle, args=(conn, state), name="merchant-mock-client", daemon=True
        ).start()


def _port_open(port: int) -> bool:
    try:
        probe = socket.create_connection((MOCK_HOST, port), timeout=0.2)
    except OSError:
        return False
    probe.close()
    return True


def _spawn(port: int) -> None:
    subprocess.Popen(
        [sys.executable, "-m", "agent_bitcoin.nostr.merchant_mock", str(port)],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )


def ensure_mock() -> None:
    port = mock_port()
    if _port_open(port):
        _announce(port)
        return
    with _LOCK:
        deadline = time.time() + 5
        while time.time() < deadline:
            if _port_open(port):
                _announce(port)
                return
            _spawn(port)
            time.sleep(0.1)
    raise SystemExit(f"mock relay failed to listen on {MOCK_HOST}:{port}")


def _announce(port: int) -> None:
    if port in _ANNOUNCED:
        return
    _ANNOUNCED.add(port)
    print(f"[relay] mock {MOCK_HOST}:{port}", flush=True)


def _connect() -> socket.socket:
    ensure_mock()
    last: Exception | None = None
    for _ in range(15):
        try:
            return socket.create_connection((MOCK_HOST, mock_port()), timeout=2)
        except OSError as exc:
            last = exc
            time.sleep(0.05)
    raise SystemExit(f"mock relay connect failed: {last}")


def _send_line(conn: socket.socket, payload: dict[str, Any]) -> None:
    conn.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode())


def _read_until(
    conn: socket.socket,
    timeout: float,
    on_msg: Callable[[dict[str, Any]], Any],
) -> Any:
    conn.settimeout(0.4)
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = conn.recv(65536)
        except TimeoutError:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode())
            except json.JSONDecodeError:
                continue
            got = on_msg(msg)
            if got is not None:
                return got
    return None


def _mock_publish(data: dict[str, Any]) -> None:
    conn = _connect()
    try:
        _send_line(conn, {"op": "pub", "event": data})

        def _on(msg: dict[str, Any]) -> bool | None:
            if msg.get("op") == "ok":
                return True
            return None

        if _read_until(conn, 3, _on) is None:
            raise SystemExit("mock relay did not ack publish")
    finally:
        conn.close()


def _mock_watch(
    pred: Callable[[dict[str, Any]], bool], timeout: float
) -> dict[str, Any] | None:
    conn = _connect()
    try:
        _send_line(conn, {"op": "watch"})

        def _on(msg: dict[str, Any]) -> dict[str, Any] | None:
            ev = msg.get("event")
            if isinstance(ev, dict) and pred(ev):
                return ev
            return None

        return _read_until(conn, timeout, _on)
    finally:
        conn.close()


def _mock_gather(
    pred: Callable[[dict[str, Any]], bool], timeout: float
) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    conn = _connect()
    try:
        _send_line(conn, {"op": "watch"})

        def _on(msg: dict[str, Any]) -> None:
            ev = msg.get("event")
            if not isinstance(ev, dict) or not pred(ev):
                return None
            eid = str(ev.get("id") or "")
            if eid in seen:
                return None
            if eid:
                seen.add(eid)
            found.append(ev)
            return None

        _read_until(conn, timeout, _on)
    finally:
        conn.close()
    return found


def _predicate(
    *,
    invoice_id: str,
    msg_type: str | None,
    role: str | None,
    since: int,
    key_dir: Path | None,
    round_n: int | None,
) -> Callable[[dict[str, Any]], bool]:
    def pred(ev: dict[str, Any]) -> bool:
        created = int(ev.get("created_at") or 0)
        if since and created < int(since) - 5:
            return False
        if not accept(ev, invoice_id, key_dir=key_dir, round_n=round_n):
            return False
        if msg_type:
            try:
                body = json.loads(ev.get("content") or "")
            except json.JSONDecodeError:
                return False
            if body.get("type") != msg_type:
                return False
        if role and _tag(ev, "role") != role:
            return False
        return True

    return pred


def _event_from_dict(data: dict[str, Any]) -> Any:
    from pynostr.event import Event

    ev = Event(
        content=data["content"],
        kind=int(data["kind"]),
        tags=data.get("tags") or [],
        pubkey=data.get("pubkey"),
    )
    if data.get("id"):
        ev.id = data["id"]
    if data.get("created_at"):
        ev.created_at = data["created_at"]
    if data.get("sig"):
        ev.sig = data["sig"]
    if data.get("pubkey"):
        ev.pubkey = data["pubkey"]
    return ev


def hold_mock() -> socket.socket:
    """Keep the localhost mock up until the caller closes the socket.

    The relay process exits only after every client, including this hold,
    has disconnected and the idle timer fires. One demo process can outlive
    a slow peer still deriving keys.
    """
    conn = _connect()
    try:
        _send_line(conn, {"op": "hold"})

        def _on(msg: dict[str, Any]) -> bool | None:
            if msg.get("op") == "ok":
                return True
            return None

        if _read_until(conn, 3, _on) is None:
            raise SystemExit("mock relay did not ack hold")
    except Exception:
        conn.close()
        raise
    return conn


def publish(event: Any, *, offline: bool) -> None:
    data = event_to_dict(event)
    try:
        body = json.loads(data.get("content") or "")
    except json.JSONDecodeError as exc:
        raise SystemExit("refusing to publish non-JSON content") from exc
    if _leaks(body):
        raise SystemExit("refusing to publish bolt11, preimage, nsec, or macaroon")
    if offline:
        _mock_publish(data)
        return
    publish_event(data)


def wait_event(
    *,
    offline: bool,
    invoice_id: str,
    msg_type: str,
    role: str | None,
    timeout: float,
    since: int,
    key_dir: Path | None,
    round_n: int | None,
) -> Any:
    pred = _predicate(
        invoice_id=invoice_id,
        msg_type=msg_type,
        role=role,
        since=since,
        key_dir=key_dir,
        round_n=round_n,
    )
    if offline:
        found = _mock_watch(pred, timeout)
    else:
        found = None
        for data in poll_events(
            None, kinds=[KIND_MERCHANT], since=max(0, int(since) - 5), timeout=timeout
        ):
            if pred(data):
                found = data
                break
    if not found:
        raise SystemExit(f"timeout waiting for {msg_type} role={role}")
    return _event_from_dict(found)


def collect_events(
    *,
    offline: bool,
    invoice_id: str,
    msg_type: str | None,
    timeout: float,
    since: int,
    key_dir: Path | None,
    round_n: int | None,
) -> list[Any]:
    pred = _predicate(
        invoice_id=invoice_id,
        msg_type=msg_type,
        role=None,
        since=since,
        key_dir=key_dir,
        round_n=round_n,
    )
    if offline:
        rows = _mock_gather(pred, timeout)
    else:
        rows = []
        try:
            for data in poll_events(
                None,
                kinds=[KIND_MERCHANT],
                since=max(0, int(since) - 5),
                timeout=timeout,
            ):
                if pred(data):
                    rows.append(data)
        except SystemExit:
            pass
    return [_event_from_dict(row) for row in rows]


def has_result(
    invoice_id: str,
    round_n: int,
    *,
    offline: bool,
    key_dir: Path | None,
) -> bool:
    try:
        ev = wait_event(
            offline=offline,
            invoice_id=invoice_id,
            msg_type="result",
            role=None,
            timeout=0.4 if offline else 2.0,
            since=0,
            key_dir=key_dir,
            round_n=int(round_n),
        )
    except SystemExit:
        return False
    try:
        body = json.loads(ev.content)
    except json.JSONDecodeError:
        return False
    return int(body.get("round") or 0) == int(round_n)
