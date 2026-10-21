"""Read-only block header for GET /paid/bitcoin/btc-block-header?height=<n>.

getblockhash then getblockheader. Does not open a wallet, send, or spend.
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
_MAX_NONCE = 4_294_967_295
_MIN_VERSION = -2_147_483_648
_MAX_VERSION = 2_147_483_647
_HEX = frozenset("0123456789abcdef")
_NOT_FOUND = frozenset({-8, -5})


class MissingHeight(Exception):
    """Query has no height."""


class BadHeight(Exception):
    """Height is negative, not an integer, or above the cap."""


class BlockNotFound(Exception):
    """Core has no block at this height."""


class BitcoindUnavailable(Exception):
    """Missing RPC config, timeout, auth failure, or bitcoind down."""


def parse_height(query: str) -> int:
    """Read one height from the query. No regex."""
    if not query:
        raise MissingHeight("missing height")
    found: str | None = None
    for part in query.split("&"):
        if part == "":
            continue
        key, sep, value = part.partition("=")
        if sep != "=" or key != "height":
            raise BadHeight("bad height")
        if found is not None:
            raise BadHeight("bad height")
        found = value
    if found is None:
        raise MissingHeight("missing height")
    text = found.strip()
    if not text or len(text) > 8 or any(ch not in "0123456789" for ch in text):
        raise BadHeight("bad height")
    number = int(text)
    if number > _MAX_HEIGHT:
        raise BadHeight("bad height")
    return number


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
    """Only getblockhash([height]) and getblockheader([hash, true])."""
    if method == "getblockhash":
        if len(params) == 1 and type(params[0]) is int:
            return
    elif method == "getblockheader":
        if len(params) == 2 and isinstance(params[0], str) and params[1] is True:
            return
    raise BitcoindUnavailable("bitcoind unavailable")


def _hex_n(value: Any, size: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != size:
        return None
    if any(ch not in _HEX for ch in text):
        return None
    return text


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


def _version(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        number = int(value)
    elif isinstance(value, str):
        text = value.strip()
        digits = text[1:] if text.startswith("-") else text
        if (
            not digits
            or len(digits) > 10
            or any(ch not in "0123456789" for ch in digits)
        ):
            return None
        number = int(text)
    else:
        return None
    if number < _MIN_VERSION or number > _MAX_VERSION:
        return None
    return number


def _summary(height: int, tip: str, raw: dict[str, Any]) -> dict[str, Any]:
    got = _hex_n(raw.get("hash"), 64)
    if got != tip:
        raise BitcoindUnavailable("getblockheader failed")
    if "height" in raw and _count(raw.get("height"), _MAX_HEIGHT) != height:
        raise BitcoindUnavailable("getblockheader failed")
    when = _count(raw.get("time"), _MAX_TIME)
    bits = _hex_n(raw.get("bits"), 8)
    nonce = _count(raw.get("nonce"), _MAX_NONCE)
    if when is None or bits is None or nonce is None:
        raise BitcoindUnavailable("getblockheader failed")
    out: dict[str, Any] = {"height": height, "hash": tip}
    if "previousblockhash" in raw:
        prev = _hex_n(raw.get("previousblockhash"), 64)
        if prev is None:
            raise BitcoindUnavailable("getblockheader failed")
        out["previousblockhash"] = prev
    out["time"] = when
    out["bits"] = bits
    out["nonce"] = nonce
    if "version" in raw:
        version = _version(raw.get("version"))
        if version is None:
            raise BitcoindUnavailable("getblockheader failed")
        out["version"] = version
    return out


def _result_from_message(parsed: Any) -> Any:
    """Unwrap one JSON-RPC object. Reads error code only."""
    if not isinstance(parsed, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    err = parsed.get("error")
    if err:
        code = err.get("code") if isinstance(err, dict) else None
        if type(code) is int and code in _NOT_FOUND:
            raise BlockNotFound("block not found")
        raise BitcoindUnavailable("bitcoind unavailable")
    if "result" not in parsed:
        raise BitcoindUnavailable("bitcoind unavailable")
    result = parsed.get("result")
    if not isinstance(result, (dict, str)):
        raise BitcoindUnavailable("bitcoind unavailable")
    return result


def handle_request(
    height: int,
    caller: Callable[[str, list[Any]], Any] | None = None,
) -> dict[str, Any]:
    """Return one header. caller injects getblockhash then getblockheader."""
    if type(height) is not int or height < 0 or height > _MAX_HEIGHT:
        raise BadHeight("bad height")
    rpc = caller if caller is not None else _rpc_from_env()
    raw_hash = _rpc_call(rpc, "getblockhash", [height])
    tip = _hex_n(raw_hash, 64)
    if tip is None:
        raise BitcoindUnavailable("getblockhash failed")
    raw_header = _rpc_call(rpc, "getblockheader", [tip, True])
    if not isinstance(raw_header, dict):
        raise BitcoindUnavailable("getblockheader failed")
    return _summary(height, tip, raw_header)


def _rpc_call(
    rpc: Callable[[str, list[Any]], Any], method: str, params: list[Any]
) -> Any:
    try:
        return rpc(method, params)
    except BlockNotFound as exc:
        raise BlockNotFound("block not found") from exc
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
                "id": "btc-block-header",
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
        return _result_from_message(parsed)

    return call
