"""Read-only soft-fork list for GET /paid/bitcoin/btc-deployment-info.

One getblockchaininfo. Does not open a wallet, send, or spend.
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
_MAX_FORKS = 16
_MAX_NAME = 32
_MAX_HEIGHT = 10_000_000
_MAX_WARNINGS = 4
_MAX_WARNING = 128


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
    """Only getblockchaininfo([])."""
    if method == "getblockchaininfo" and params == []:
        return
    raise BitcoindUnavailable("bitcoind unavailable")


def _count(value: Any, low: int, high: int) -> int | None:
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
    if number < low or number > high:
        return None
    return number


def _name(value: Any) -> str | None:
    if not isinstance(value, str) or not value or len(value) > _MAX_NAME:
        return None
    for ch in value:
        if not (("a" <= ch <= "z") or ("0" <= ch <= "9")):
            return None
    return value


def _status(body: dict[str, Any]) -> str:
    """bip9.status when present. Buried forks use the word active."""
    if "bip9" not in body:
        return "active"
    bip9 = body["bip9"]
    if not isinstance(bip9, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    if "status" not in bip9:
        return "active"
    if bip9["status"] != "active":
        raise BitcoindUnavailable("bitcoind unavailable")
    return "active"


def _one_height(value: Any) -> int:
    number = _count(value, 0, _MAX_HEIGHT)
    if number is None:
        raise BitcoindUnavailable("bitcoind unavailable")
    return number


def _height(body: dict[str, Any]) -> int | None:
    """Core height, else bip9 min_activation_height, else bip9 since."""
    if "height" in body:
        return _one_height(body["height"])
    bip9 = body.get("bip9")
    if not isinstance(bip9, dict):
        return None
    if "min_activation_height" in bip9:
        return _one_height(bip9["min_activation_height"])
    if "since" in bip9:
        return _one_height(bip9["since"])
    return None


def _entries(softforks: Any) -> list[tuple[Any, Any]]:
    """Object key order, or an array of objects that carry name."""
    if isinstance(softforks, dict):
        return list(softforks.items())
    if isinstance(softforks, list):
        rows: list[tuple[Any, Any]] = []
        for body in softforks:
            if not isinstance(body, dict):
                raise BitcoindUnavailable("bitcoind unavailable")
            rows.append((body.get("name"), body))
        return rows
    raise BitcoindUnavailable("bitcoind unavailable")


def _fork_rows(softforks: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, body in _entries(softforks):
        if not isinstance(body, dict):
            raise BitcoindUnavailable("bitcoind unavailable")
        if "active" not in body:
            continue
        active = body["active"]
        if not isinstance(active, bool):
            raise BitcoindUnavailable("bitcoind unavailable")
        if not active:
            continue
        clean = _name(name)
        if clean is None:
            raise BitcoindUnavailable("bitcoind unavailable")
        row: dict[str, Any] = {"name": clean, "status": _status(body)}
        height = _height(body)
        if height is not None:
            row["height"] = height
        rows.append(row)
        if len(rows) > _MAX_FORKS:
            raise BitcoindUnavailable("bitcoind unavailable")
    return rows


def _warning_text(value: Any) -> str | None:
    """None drops an empty warning. A bad character fails the response."""
    if not isinstance(value, str):
        raise BitcoindUnavailable("bitcoind unavailable")
    text = value.strip()
    if not text:
        return None
    for ch in text:
        if ch < " " or ch > "~":
            raise BitcoindUnavailable("bitcoind unavailable")
    return text[:_MAX_WARNING]


def _warnings(raw: dict[str, Any]) -> list[str] | None:
    if "warnings" not in raw:
        return None
    value = raw["warnings"]
    if isinstance(value, str):
        items: list[Any] = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise BitcoindUnavailable("bitcoind unavailable")
    kept: list[str] = []
    for item in items:
        text = _warning_text(item)
        if text is None:
            continue
        kept.append(text)
    if not kept:
        return None
    return kept[:_MAX_WARNINGS]


def _summary(raw: dict[str, Any]) -> dict[str, Any]:
    if "softforks" not in raw:
        raise BitcoindUnavailable("bitcoind unavailable")
    out: dict[str, Any] = {"softforks": _fork_rows(raw["softforks"])}
    warnings = _warnings(raw)
    if warnings is not None:
        out["warnings"] = warnings
    return out


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
    """Return active soft-forks. caller injects getblockchaininfo."""
    rpc = caller if caller is not None else _rpc_from_env()
    raw = _rpc_call(rpc, "getblockchaininfo", [])
    if not isinstance(raw, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    return _summary(raw)


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
                "id": "btc-deployment-info",
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
