"""Standalone localhost mock relay. Stdlib only.

Run this file directly so startup does not import the agent_bitcoin package
(that import is too slow for CI). Binds 127.0.0.1 only.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from typing import Any

MOCK_HOST = "127.0.0.1"


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
    conn.sendall((json.dumps(payload, separators=(",", ":")) + "\n").encode())


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
    """Block until idle with zero clients, then exit."""
    state = _ServerState()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((MOCK_HOST, int(port)))
    except OSError as exc:
        print(f"bind {MOCK_HOST}:{port} failed: {exc}", file=sys.stderr)
        return
    sock.listen(64)
    sock.settimeout(0.5)
    try:
        idle_s = float((os.environ.get("MERCHANT_MOCK_IDLE") or "60").strip())
    except ValueError:
        idle_s = 60.0

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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(f"usage: {sys.argv[0]} PORT", file=sys.stderr)
        return 2
    serve_forever(int(args[0]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
