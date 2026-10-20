"""Read-only fee estimates for GET /paid/bitcoin/btc-fee-estimate.

estimatesmartfee only. Does not open a wallet, send, or spend.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

TARGETS = (1, 3, 6)
_TIMEOUT_S = 5.0
_MAX_SAT_VB = Decimal(100_000)
_BTC_KVB_TO_SAT_VB = Decimal(100_000)
_NOTE = "estimate_unavailable"
_METHOD = "estimatesmartfee"
_MAX_BODY = 65536


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


def _sats_per_vb(feerate: Any) -> int | float | None:
    if isinstance(feerate, bool) or feerate is None:
        return None
    if isinstance(feerate, Decimal):
        dec = feerate
    elif isinstance(feerate, int):
        dec = Decimal(feerate)
    elif isinstance(feerate, str):
        text = feerate.strip()
        if not text or text.count(".") > 1:
            return None
        for ch in text:
            if ch not in "0123456789.":
                return None
        try:
            dec = Decimal(text)
        except ArithmeticError:
            return None
    else:
        return None
    if dec < 0:
        return None
    sats = (dec * _BTC_KVB_TO_SAT_VB).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if sats < 0 or sats > _MAX_SAT_VB:
        return None
    if sats == sats.to_integral_value():
        return int(sats)
    return float(sats)


def _blocks(raw: Any, requested: int) -> int:
    if isinstance(raw, bool) or raw is None:
        return requested
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, Decimal) and raw == raw.to_integral_value() and raw > 0:
        return int(raw)
    if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
        return int(raw)
    return requested


def _row(requested: int, result: dict[str, Any]) -> dict[str, Any]:
    blocks = _blocks(result.get("blocks"), requested)
    rate = None if "errors" in result else _sats_per_vb(result.get("feerate"))
    if rate is None:
        return {
            "blocks": blocks,
            "feerate_sats_per_vb": None,
            "note": _NOTE,
        }
    return {"blocks": blocks, "feerate_sats_per_vb": rate}


def handle_request(
    caller: Callable[[int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return estimates for 1, 3, and 6 blocks. caller injects a mock RPC result."""
    rpc = caller if caller is not None else _rpc_from_env()
    rows: list[dict[str, Any]] = []
    for target in TARGETS:
        try:
            result = rpc(target)
        except BitcoindUnavailable:
            raise
        except Exception as exc:
            raise BitcoindUnavailable("estimatesmartfee failed") from exc
        if not isinstance(result, dict):
            raise BitcoindUnavailable("estimatesmartfee failed")
        rows.append(_row(target, result))
    return {"estimates": rows}


def _rpc_from_env() -> Callable[[int], dict[str, Any]]:
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

    def call(conf_target: int) -> dict[str, Any]:
        if conf_target not in TARGETS:
            raise BitcoindUnavailable("estimatesmartfee failed")
        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "btc-fee-estimate",
                "method": _METHOD,
                "params": [conf_target],
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
