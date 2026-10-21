"""Read-only chain tips for GET /paid/bitcoin/btc-chain-tips.

getchaintips only. Does not open a wallet, send, or spend.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from decimal import Decimal
from typing import Any, Callable

_TIMEOUT_S = 5.0
_MAX_BODY = 65536
_MAX_TIPS = 16
_MAX_HEIGHT = 10_000_000
_HEX = frozenset("0123456789abcdef")
_STATUSES = frozenset(
    {"active", "invalid", "headers-only", "valid-headers", "valid-fork"}
)


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


def _allow(method: str, params: list[Any]) -> None:
    """Only getchaintips([])."""
    if method == "getchaintips" and params == []:
        return
    raise BitcoindUnavailable("bitcoind unavailable")


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        number = int(value)
    elif (
        isinstance(value, str)
        and value.isdigit()
        and len(value) <= len(str(_MAX_HEIGHT))
    ):
        number = int(value)
    else:
        return None
    if number < 0 or number > _MAX_HEIGHT:
        return None
    return number


def _hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 64:
        return None
    for ch in text:
        if ch not in _HEX:
            return None
    return text


def _rows(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or len(raw) > _MAX_TIPS:
        raise BitcoindUnavailable("bitcoind unavailable")
    rows: list[dict[str, Any]] = []
    active = 0
    for item in raw:
        if not isinstance(item, dict):
            raise BitcoindUnavailable("bitcoind unavailable")
        height = _count(item.get("height"))
        digest = _hash(item.get("hash"))
        branch = _count(item.get("branchlen"))
        status = item.get("status")
        if (
            height is None
            or digest is None
            or branch is None
            or not isinstance(status, str)
            or status not in _STATUSES
        ):
            raise BitcoindUnavailable("bitcoind unavailable")
        is_active = status == "active"
        if is_active:
            active += 1
        rows.append(
            {
                "height": height,
                "hash": digest,
                "branchlen": branch,
                "status": status,
                "active": is_active,
            }
        )
    if rows and active != 1:
        raise BitcoindUnavailable("bitcoind unavailable")
    return rows


def _result_from_message(parsed: Any) -> Any:
    """Unwrap one JSON-RPC object. Drops the error text."""
    if not isinstance(parsed, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    if parsed.get("error"):
        raise BitcoindUnavailable("bitcoind unavailable")
    if "result" not in parsed:
        raise BitcoindUnavailable("bitcoind unavailable")
    return parsed.get("result")


def handle_request(
    caller: Callable[[str, list[Any]], Any] | None = None,
) -> dict[str, Any]:
    """Return chain tips. The active tip has active true."""
    rpc = caller if caller is not None else _rpc_from_env()
    raw = _rpc_call(rpc, "getchaintips", [])
    return {"tips": _rows(raw)}


def _rpc_call(
    rpc: Callable[[str, list[Any]], Any], method: str, params: list[Any]
) -> Any:
    try:
        return rpc(method, params)
    except BitcoindUnavailable:
        raise
    except Exception as exc:
        raise BitcoindUnavailable("bitcoind unavailable") from exc


def _rpc_from_env() -> Callable[[str, list[Any]], Any]:
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

    def call(method: str, params: list[Any]) -> Any:
        _allow(method, params)
        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "btc-chain-tips",
                "method": method,
                "params": params,
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
        return _result_from_message(parsed)

    return call
