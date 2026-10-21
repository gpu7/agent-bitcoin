"""Read-only mempool fees for GET /paid/bitcoin/btc-mempool-fees.

getmempoolinfo, then estimatesmartfee for 1, 3, and 6 blocks.
Does not open a wallet, send, or spend.
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
_MAX_SIZE = 10_000_000
_MAX_MIN_FEE = Decimal(1)
_SATOSHI = Decimal("0.00000001")
_TARGETS = (1, 3, 6)
_BTC_KVB_TO_SAT_VB = Decimal(100_000)
_MAX_SAT_VB = Decimal(100_000)
_SAT_QUANT = Decimal("0.01")


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
    """getmempoolinfo([]) and estimatesmartfee for 1, 3, or 6 blocks."""
    if method == "getmempoolinfo" and params == []:
        return
    if method == "estimatesmartfee" and params in ([1], [3], [6]):
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
        isinstance(value, str) and value.isdigit() and len(value) <= len(str(_MAX_SIZE))
    ):
        number = int(value)
    else:
        return None
    if number < 0 or number > _MAX_SIZE:
        return None
    return number


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        text = value.strip()
        if not text or text.count(".") > 1:
            return None
        if any(ch not in "0123456789." for ch in text):
            return None
        try:
            return Decimal(text)
        except ArithmeticError:
            return None
    return None


def _btc(value: Any) -> int | float | None:
    dec = _decimal(value)
    if dec is None or not dec.is_finite() or dec < 0 or dec > _MAX_MIN_FEE:
        return None
    quant = dec.quantize(_SATOSHI, rounding=ROUND_HALF_UP)
    if quant < 0 or quant > _MAX_MIN_FEE:
        return None
    if quant == quant.to_integral_value():
        return int(quant)
    return float(quant)


def _sats_per_vb(value: Any) -> int | float | None:
    dec = _decimal(value)
    if dec is None or not dec.is_finite() or dec < 0:
        return None
    sats = (dec * _BTC_KVB_TO_SAT_VB).quantize(_SAT_QUANT, rounding=ROUND_HALF_UP)
    if sats < 0 or sats > _MAX_SAT_VB:
        return None
    if sats == sats.to_integral_value():
        return int(sats)
    return float(sats)


def _band(target: int, result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    if "errors" in result or "feerate" not in result:
        return None
    rate = _sats_per_vb(result.get("feerate"))
    if rate is None:
        return None
    return {"blocks": target, "feerate_sats_per_vb": rate}


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
    """Return mempool size, minimum fee, and any available fee bands."""
    rpc = caller if caller is not None else _rpc_from_env()
    raw = _rpc_call(rpc, "getmempoolinfo", [])
    if not isinstance(raw, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    size = _count(raw.get("size"))
    min_fee = _btc(raw.get("mempoolminfee"))
    if size is None or min_fee is None:
        raise BitcoindUnavailable("bitcoind unavailable")
    bands: list[dict[str, Any]] = []
    for target in _TARGETS:
        row = _band(target, _rpc_call(rpc, "estimatesmartfee", [target]))
        if row is not None:
            bands.append(row)
    out: dict[str, Any] = {"size": size, "mempoolminfee": min_fee}
    if bands:
        out["fee_bands"] = bands
    return out


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
                "id": "btc-mempool-fees",
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
