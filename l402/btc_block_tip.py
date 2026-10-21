"""Read-only chain tip for GET /paid/bitcoin/btc-block-tip.

getblockchaininfo only. Does not open a wallet, send, or spend.
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
_MAX_HEIGHT = 10_000_000
_MAX_TIME = 10_000_000_000
_METHOD = "getblockchaininfo"
_HEX = frozenset("0123456789abcdef")


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


def _count(value: Any, high: int) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        number = int(value)
    elif isinstance(value, str) and value.isdigit() and len(value) <= len(str(high)):
        number = int(value)
    else:
        return None
    if number < 0 or number > high:
        return None
    return number


def _block_hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 64:
        return None
    if any(ch not in _HEX for ch in text):
        return None
    return text


def _summary(raw: dict[str, Any]) -> dict[str, Any]:
    height = _count(raw.get("blocks"), _MAX_HEIGHT)
    tip = _block_hash(raw.get("bestblockhash"))
    if height is None or tip is None:
        raise BitcoindUnavailable("getblockchaininfo failed")
    out: dict[str, Any] = {"height": height, "best_block_hash": tip}
    if "mediantime" in raw:
        when = _count(raw.get("mediantime"), _MAX_TIME)
        if when is None:
            raise BitcoindUnavailable("getblockchaininfo failed")
        out["median_time"] = when
    return out


def handle_request(
    caller: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return height, the public tip hash, and median time when Core sends it."""
    rpc = caller if caller is not None else _rpc_from_env()
    try:
        result = rpc()
    except BitcoindUnavailable:
        raise
    except Exception as exc:
        raise BitcoindUnavailable("getblockchaininfo failed") from exc
    if not isinstance(result, dict):
        raise BitcoindUnavailable("getblockchaininfo failed")
    return _summary(result)


def _rpc_from_env() -> Callable[[], dict[str, Any]]:
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

    def call() -> dict[str, Any]:
        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "btc-block-tip",
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
            if resp.status != 200:
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
        if not isinstance(result, dict):
            raise BitcoindUnavailable("bitcoind unavailable")
        return result

    return call
