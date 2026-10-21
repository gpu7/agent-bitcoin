"""Read-only address balance for POST /paid/bitcoin/btc-address-balance.

scantxoutset start with one addr() descriptor. Does not open a wallet,
unlock, send, or spend. Confirmed UTXOs only.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

try:
    from l402.btc_address_validate import validate as _validate_address
except ImportError:  # Docker WORKDIR /app
    from btc_address_validate import validate as _validate_address  # type: ignore[no-redef]

_SCAN_TIMEOUT_S = 120.0
_ABORT_TIMEOUT_S = 5.0
_MAX_BODY = 1_048_576
_ABORT_BODY = 65536
_REQUEST_BODY = 512
_MAX_BTC = Decimal(21_000_000)
_SATOSHI = Decimal("0.00000001")
_COIN = Decimal(100_000_000)
_MAX_SATS = 2_100_000_000_000_000
_CHAINS = frozenset({"mainnet", "regtest", "signet", "testnet"})
_BASE58_KINDS = frozenset({"p2pkh", "p2sh"})
_ADDR_CHARS = frozenset(
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
)
_DESC_BAD = frozenset("()[],\\\"' \t\r\n")


class MissingAddress(Exception):
    """Body is not a JSON object or address is missing."""


class BadAddress(Exception):
    """Address is invalid or for another network."""


class BitcoindUnavailable(Exception):
    """Missing RPC config, timeout, auth failure, or bitcoind down."""


def parse_request(body: bytes) -> str:
    """Read one address from the JSON body. No RPC."""
    return _accept(_read_address(body))


def _read_address(body: bytes) -> str:
    if not isinstance(body, (bytes, bytearray)) or len(body) > _REQUEST_BODY:
        raise MissingAddress("missing address")
    try:
        payload = json.loads(bytes(body).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MissingAddress("missing address") from exc
    if not isinstance(payload, dict) or "address" not in payload:
        raise MissingAddress("missing address")
    address = payload.get("address")
    if not isinstance(address, str):
        raise MissingAddress("missing address")
    return address.strip()


def _chain() -> str:
    return os.environ.get("L402_NETWORK", "regtest").strip() or "regtest"


def _matches(info: dict[str, Any], chain: str) -> bool:
    network = info.get("network")
    kind = info.get("address_type")
    if chain == "mainnet":
        return network == "mainnet"
    if chain == "regtest":
        if network == "regtest":
            return True
        return network == "testnet" and kind in _BASE58_KINDS
    if chain in {"signet", "testnet"}:
        return network == "testnet"
    return False


def _accept(text: str) -> str:
    if not text or any(ch in _DESC_BAD for ch in text):
        raise BadAddress("bad address")
    info = _validate_address(text)
    if not isinstance(info, dict) or info.get("valid") is not True:
        raise BadAddress("bad address")
    chain = _chain()
    if chain not in _CHAINS:
        raise BitcoindUnavailable("bitcoind unavailable")
    if not _matches(info, chain):
        raise BadAddress("bad address")
    return text


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


def _addr_desc(value: Any) -> bool:
    if not isinstance(value, str) or len(value) > 96:
        return False
    if not value.startswith("addr(") or not value.endswith(")"):
        return False
    inner = value[5:-1]
    if not inner or len(inner) > 90:
        return False
    return all(ch in _ADDR_CHARS for ch in inner)


def _allow(method: str, params: list[Any]) -> None:
    """Only scantxoutset start of one addr(), or abort."""
    if method != "scantxoutset":
        raise BitcoindUnavailable("bitcoind unavailable")
    if len(params) == 1 and params[0] == "abort":
        return
    if (
        len(params) == 2
        and params[0] == "start"
        and isinstance(params[1], list)
        and len(params[1]) == 1
        and _addr_desc(params[1][0])
    ):
        return
    raise BitcoindUnavailable("bitcoind unavailable")


def _amount(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, int):
        dec = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text or len(text) > 32 or text.count(".") > 1:
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
    if dec < 0 or dec > _MAX_BTC:
        return None
    quant = dec.quantize(_SATOSHI, rounding=ROUND_HALF_UP)
    if quant < 0 or quant > _MAX_BTC:
        return None
    return quant


def _sats(value: Any) -> int | None:
    quant = _amount(value)
    if quant is None:
        return None
    sats = int((quant * _COIN).to_integral_value())
    if sats < 0 or sats > _MAX_SATS:
        return None
    return sats


def _summary(address: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("success") is not True:
        raise BitcoindUnavailable("bitcoind unavailable")
    if "total_amount" not in raw:
        raise BitcoindUnavailable("bitcoind unavailable")
    sats = _sats(raw.get("total_amount"))
    if sats is None:
        raise BitcoindUnavailable("bitcoind unavailable")
    out: dict[str, Any] = {"address": address, "balance_sats": sats}
    if sats == 0:
        out["note"] = "no confirmed outputs"
    return out


def _result_from_message(parsed: Any) -> Any:
    """Unwrap one JSON-RPC object. Drops the error text."""
    if not isinstance(parsed, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    err = parsed.get("error")
    if err:
        raise BitcoindUnavailable("bitcoind unavailable")
    if "result" not in parsed:
        raise BitcoindUnavailable("bitcoind unavailable")
    return parsed.get("result")


def handle_request(
    address: str,
    caller: Callable[[str, list[Any]], Any] | None = None,
) -> dict[str, Any]:
    """Return one confirmed balance. caller injects scantxoutset."""
    if not isinstance(address, str):
        raise BadAddress("bad address")
    text = _accept(address.strip())
    rpc = caller if caller is not None else _rpc_from_env()
    raw = _rpc_call(rpc, "scantxoutset", ["start", ["addr(" + text + ")"]])
    return _summary(text, raw)


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

    def exchange(method: str, params: list[Any], timeout: float, cap: int) -> Any:
        _allow(method, params)
        payload = json.dumps(
            {
                "jsonrpc": "1.0",
                "id": "btc-address-balance",
                "method": method,
                "params": params,
            }
        ).encode("utf-8")
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
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
            body = resp.read(cap)
            if resp.status != 200 or len(body) >= cap:
                raise BitcoindUnavailable("bitcoind unavailable")
        except BitcoindUnavailable:
            raise
        except TimeoutError:
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

    def call(method: str, params: list[Any]) -> Any:
        start = method == "scantxoutset" and bool(params) and params[0] == "start"
        try:
            return exchange(
                method,
                params,
                _SCAN_TIMEOUT_S if start else _ABORT_TIMEOUT_S,
                _MAX_BODY if start else _ABORT_BODY,
            )
        except TimeoutError:
            if start:
                try:
                    exchange(
                        "scantxoutset",
                        ["abort"],
                        _ABORT_TIMEOUT_S,
                        _ABORT_BODY,
                    )
                except Exception:
                    pass
            raise BitcoindUnavailable("bitcoind unavailable")

    return call
