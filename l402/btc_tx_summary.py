"""Read-only transaction summary for GET /paid/bitcoin/btc-tx-summary?txid=<hex>.

getrawtransaction verbose, then getmempoolentry only when unconfirmed.
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
_RAW_BODY = 1_048_576
_ENTRY_BODY = 65536
_MAX_CONF = 10_000_000
_MAX_VSIZE = 1_000_000
_MAX_IO = 100_000
_MAX_FEE_BTC = Decimal(21_000_000)
_SATOSHI = Decimal("0.00000001")
_HEX = frozenset("0123456789abcdef")


class MissingTxid(Exception):
    """Query has no txid."""


class BadTxid(Exception):
    """Txid is not 64 hex characters."""


class TxNotFound(Exception):
    """Core has no such transaction, or it left the mempool."""


class BitcoindUnavailable(Exception):
    """Missing RPC config, timeout, auth failure, or bitcoind down."""


def parse_txid(query: str) -> str:
    """Read one txid from the query. No regex."""
    if not query:
        raise MissingTxid("missing txid")
    found: str | None = None
    for part in query.split("&"):
        if part == "":
            continue
        key, sep, value = part.partition("=")
        if sep != "=" or key != "txid":
            raise BadTxid("bad txid")
        if found is not None:
            raise BadTxid("bad txid")
        found = value
    if found is None:
        raise MissingTxid("missing txid")
    return _require_txid(found)


def _require_txid(value: Any) -> str:
    text = _hex64(value)
    if text is None:
        raise BadTxid("bad txid")
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


def _hex64(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 64 or any(ch not in _HEX for ch in text):
        return None
    return text


def _allow(method: str, params: list[Any]) -> None:
    """Only getrawtransaction([txid, true]) and getmempoolentry([txid])."""
    if method == "getrawtransaction":
        if len(params) == 2 and _hex64(params[0]) is not None and params[1] is True:
            return
    elif method == "getmempoolentry":
        if len(params) == 1 and _hex64(params[0]) is not None:
            return
    raise BitcoindUnavailable("bitcoind unavailable")


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


def _btc(value: Any) -> int | float | None:
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
    if dec < 0 or dec > _MAX_FEE_BTC:
        return None
    quant = dec.quantize(_SATOSHI, rounding=ROUND_HALF_UP)
    if quant < 0 or quant > _MAX_FEE_BTC:
        return None
    if quant == quant.to_integral_value():
        return int(quant)
    return float(quant)


def _fields(txid: str, raw: Any) -> tuple[int, int, int, int]:
    """confirmations, vsize, input_count, output_count. Drops scripts."""
    if not isinstance(raw, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    if "txid" in raw and _hex64(raw.get("txid")) != txid:
        raise BitcoindUnavailable("bitcoind unavailable")
    if "confirmations" in raw:
        conf = _count(raw.get("confirmations"), _MAX_CONF)
        if conf is None:
            raise BitcoindUnavailable("bitcoind unavailable")
    else:
        conf = 0
    vsize = _count(raw.get("vsize"), _MAX_VSIZE)
    vin = raw.get("vin")
    vout = raw.get("vout")
    if (
        vsize is None
        or not isinstance(vin, list)
        or not isinstance(vout, list)
        or len(vin) > _MAX_IO
        or len(vout) > _MAX_IO
    ):
        raise BitcoindUnavailable("bitcoind unavailable")
    return conf, vsize, len(vin), len(vout)


def _require_fee(entry: Any) -> int | float:
    if not isinstance(entry, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    fees = entry.get("fees")
    if not isinstance(fees, dict) or "base" not in fees:
        raise BitcoindUnavailable("bitcoind unavailable")
    amount = _btc(fees.get("base"))
    if amount is None:
        raise BitcoindUnavailable("bitcoind unavailable")
    return amount


def _result_from_message(parsed: Any, method: str) -> Any:
    """Unwrap one JSON-RPC object. Reads the error code only."""
    if not isinstance(parsed, dict):
        raise BitcoindUnavailable("bitcoind unavailable")
    err = parsed.get("error")
    if err:
        code = err.get("code") if isinstance(err, dict) else None
        if type(code) is int and code == -5:
            if method == "getrawtransaction" or method == "getmempoolentry":
                raise TxNotFound("tx not found")
        raise BitcoindUnavailable("bitcoind unavailable")
    if "result" not in parsed:
        raise BitcoindUnavailable("bitcoind unavailable")
    return parsed.get("result")


def handle_request(
    txid: str,
    caller: Callable[[str, list[Any]], Any] | None = None,
) -> dict[str, Any]:
    """Return one summary. caller injects getrawtransaction then getmempoolentry."""
    checked = _require_txid(txid)
    rpc = caller if caller is not None else _rpc_from_env()
    raw = _rpc_call(rpc, "getrawtransaction", [checked, True])
    conf, vsize, inputs, outputs = _fields(checked, raw)
    fee: int | float | None = None
    if conf == 0:
        try:
            entry = _rpc_call(rpc, "getmempoolentry", [checked])
        except TxNotFound:
            entry = None
        if entry is not None:
            fee = _require_fee(entry)
    out: dict[str, Any] = {
        "txid": checked,
        "confirmations": conf,
        "vsize": vsize,
        "input_count": inputs,
        "output_count": outputs,
    }
    if fee is not None:
        out["fee_btc"] = fee
    return out


def _rpc_call(
    rpc: Callable[[str, list[Any]], Any], method: str, params: list[Any]
) -> Any:
    try:
        return rpc(method, params)
    except TxNotFound as exc:
        raise TxNotFound("tx not found") from exc
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
                "id": "btc-tx-summary",
                "method": method,
                "params": params,
            }
        ).encode("utf-8")
        cap = _RAW_BODY if method == "getrawtransaction" else _ENTRY_BODY
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
            body = resp.read(cap)
            if resp.status != 200 or len(body) >= cap:
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
        return _result_from_message(parsed, method)

    return call
