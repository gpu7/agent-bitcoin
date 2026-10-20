"""Read-only chain status for GET /paid/bitcoin/btc-chain-status.

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
_METHOD = "getblockchaininfo"
_CHAINS = ("main", "test", "signet", "regtest")


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


def _height(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, Decimal) and value == value.to_integral_value():
        number = int(value)
    elif isinstance(value, str) and value.isdigit() and len(value) <= 8:
        number = int(value)
    else:
        return None
    if number < 0 or number > _MAX_HEIGHT:
        return None
    return number


def _progress(value: Any) -> int | float | None:
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
        for ch in text:
            if ch not in "0123456789.":
                return None
        try:
            dec = Decimal(text)
        except ArithmeticError:
            return None
    else:
        return None
    if dec < 0 or dec > 1:
        return None
    if dec == dec.to_integral_value():
        return int(dec)
    return float(dec)


def _summary(raw: dict[str, Any]) -> dict[str, Any]:
    blocks = _height(raw.get("blocks"))
    headers = _height(raw.get("headers"))
    progress = _progress(raw.get("verificationprogress"))
    ibd = raw.get("initialblockdownload")
    chain = raw.get("chain")
    pruned = raw.get("pruned")
    if (
        blocks is None
        or headers is None
        or progress is None
        or not isinstance(ibd, bool)
        or not isinstance(pruned, bool)
        or not isinstance(chain, str)
        or chain not in _CHAINS
    ):
        raise BitcoindUnavailable("getblockchaininfo failed")
    out: dict[str, Any] = {
        "blocks": blocks,
        "headers": headers,
        "verificationprogress": progress,
        "initialblockdownload": ibd,
        "chain": chain,
        "pruned": pruned,
    }
    if pruned:
        pruneheight = _height(raw.get("pruneheight"))
        if pruneheight is not None:
            out["pruneheight"] = pruneheight
    return out


def handle_request(
    caller: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a small getblockchaininfo summary. caller injects a mock result."""
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
                "id": "btc-chain-status",
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
