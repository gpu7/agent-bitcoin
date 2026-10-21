"""Read-only mining summary for GET /paid/bitcoin/btc-mining-info.

getmininginfo only. Does not open a wallet, send, or spend.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

_TIMEOUT_S = 5.0
_MAX_BODY = 65536
_MAX_COUNT = 10_000_000
_MAX_NUMBER = Decimal(10) ** 40
_QUANT = Decimal("0.00000001")


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
    """Only getmininginfo([])."""
    if method == "getmininginfo" and params == []:
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
        and len(value) <= len(str(_MAX_COUNT))
    ):
        number = int(value)
    else:
        return None
    if number < 0 or number > _MAX_COUNT:
        return None
    return number


def _number(value: Any, *, allow_zero: bool) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text or text.count(".") > 1:
            return None
        if any(ch not in "0123456789." for ch in text):
            return None
        try:
            dec = Decimal(text)
        except ArithmeticError:
            return None
    else:
        return None
    if not dec.is_finite() or dec < 0 or dec > _MAX_NUMBER:
        return None
    if dec == 0 and not allow_zero:
        return None
    quant = dec.quantize(_QUANT, rounding=ROUND_HALF_UP)
    if quant < 0 or quant > _MAX_NUMBER:
        return None
    if quant == 0 and not allow_zero:
        return None
    if quant == quant.to_integral_value():
        return int(quant)
    return float(quant)


def _summary(raw: dict[str, Any]) -> dict[str, Any]:
    blocks = _count(raw.get("blocks"))
    difficulty = _number(raw.get("difficulty"), allow_zero=False)
    hashrate = _number(raw.get("networkhashps"), allow_zero=True)
    pooled = _count(raw.get("pooledtx"))
    if blocks is None or difficulty is None or hashrate is None or pooled is None:
        raise BitcoindUnavailable("bitcoind unavailable")
    return {
        "blocks": blocks,
        "difficulty": difficulty,
        "networkhashps": hashrate,
        "pooledtx": pooled,
    }


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
    """Return blocks, difficulty, hashrate, and pooled tx count."""
    rpc = caller if caller is not None else _rpc_from_env()
    raw = _rpc_call(rpc, "getmininginfo", [])
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
                "id": "btc-mining-info",
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
