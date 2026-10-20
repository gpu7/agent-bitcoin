"""Read-only peer summary for GET /paid/bitcoin/btc-peer-info.

getpeerinfo only. Does not open a wallet, send, or spend.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from decimal import Decimal
from typing import Any, Callable

_TIMEOUT_S = 5.0
_MAX_BODY = 1_048_576
_METHOD = "getpeerinfo"
_MAX_PEERS = 512
_MAX_LISTED = 8
_MAX_ADDRESS = 80
_MAX_SUBVERSION = 64


class BitcoindUnavailable(Exception):
    """Missing RPC config, timeout, auth failure, or bitcoind down."""


def _hostname(value: str) -> str:
    """Hostname only. No scheme, userinfo, slash, or port."""
    host = value.strip()
    if not host or len(host) > 253 or any(c in host for c in "@/:\\?# \t"):
        raise BitcoindUnavailable("bitcoind unavailable")
    labels = host.split(".")
    for label in labels:
        if not label or len(label) > 63:
            raise BitcoindUnavailable("bitcoind unavailable")
        if label.startswith("-") or label.endswith("-"):
            raise BitcoindUnavailable("bitcoind unavailable")
        for ch in label:
            ok = ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch == "-"
            ok = ok or ("0" <= ch <= "9")
            if not ok:
                raise BitcoindUnavailable("bitcoind unavailable")
    return host


def _port(value: str) -> int:
    raw = value.strip()
    if not raw or len(raw) > 5 or not raw.isdigit():
        raise BitcoindUnavailable("bitcoind unavailable")
    port = int(raw)
    if port < 1 or port > 65535:
        raise BitcoindUnavailable("bitcoind unavailable")
    return port


def _printable(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for ch in text:
        if ch < " " or ch > "~":
            return None
    return text


def _address(value: Any) -> str | None:
    text = _printable(value)
    if text is None or len(text) > _MAX_ADDRESS:
        return None
    for ch in text:
        if ch in "@/ ":
            return None
    return text


def _subversion(value: Any) -> str | None:
    text = _printable(value)
    if text is None:
        return None
    return text[:_MAX_SUBVERSION]


def _summary(peers: list[Any]) -> dict[str, Any]:
    if len(peers) > _MAX_PEERS:
        raise BitcoindUnavailable("getpeerinfo failed")
    inbound = 0
    outbound = 0
    rows: list[dict[str, str]] = []
    for peer in peers:
        if not isinstance(peer, dict):
            raise BitcoindUnavailable("getpeerinfo failed")
        flag = peer.get("inbound")
        if not isinstance(flag, bool):
            raise BitcoindUnavailable("getpeerinfo failed")
        if flag:
            inbound += 1
        else:
            outbound += 1
        if len(rows) >= _MAX_LISTED:
            continue
        row: dict[str, str] = {}
        address = _address(peer.get("addr"))
        subversion = _subversion(peer.get("subver"))
        if address is not None:
            row["address"] = address
        if subversion is not None:
            row["subversion"] = subversion
        if row:
            rows.append(row)
    return {
        "num_peers": len(peers),
        "inbound": inbound,
        "outbound": outbound,
        "peers": rows,
    }


def handle_request(
    caller: Callable[[], list[Any]] | None = None,
) -> dict[str, Any]:
    """Return a small getpeerinfo summary. caller injects a mock result."""
    rpc = caller if caller is not None else _rpc_from_env()
    try:
        result = rpc()
    except BitcoindUnavailable:
        raise
    except Exception as exc:
        raise BitcoindUnavailable("getpeerinfo failed") from exc
    if not isinstance(result, list):
        raise BitcoindUnavailable("getpeerinfo failed")
    return _summary(result)


def _rpc_from_env() -> Callable[[], list[Any]]:
    host_raw = os.environ.get("BITCOIND_RPC_HOST", "")
    port_raw = os.environ.get("BITCOIND_RPC_PORT", "")
    user = os.environ.get("BITCOIND_RPC_USER", "")
    password = os.environ.get("BITCOIND_RPC_PASSWORD", "")
    if not host_raw.strip() or not port_raw.strip() or user == "" or password == "":
        raise BitcoindUnavailable("bitcoind unavailable")
    host = _hostname(host_raw)
    port = _port(port_raw)
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    auth = f"Basic {token}"

    def call() -> list[Any]:
        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "btc-peer-info",
                "method": _METHOD,
                "params": [],
            }
        ).encode("utf-8")
        conn = http.client.HTTPConnection(host, port, timeout=_TIMEOUT_S)
        try:
            conn.request(
                "POST",
                "/",
                body=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": auth,
                },
            )
            resp = conn.getresponse()
            body = resp.read(_MAX_BODY)
            if resp.status != 200 or len(body) >= _MAX_BODY:
                raise BitcoindUnavailable("bitcoind unavailable")
        except BitcoindUnavailable:
            raise
        except Exception as exc:
            raise BitcoindUnavailable("bitcoind unavailable") from exc
        finally:
            conn.close()
        try:
            parsed = json.loads(body.decode("utf-8"), parse_float=Decimal)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise BitcoindUnavailable("bitcoind unavailable") from exc
        if not isinstance(parsed, dict) or parsed.get("error"):
            raise BitcoindUnavailable("bitcoind unavailable")
        result = parsed.get("result")
        if not isinstance(result, list):
            raise BitcoindUnavailable("bitcoind unavailable")
        return result

    return call
