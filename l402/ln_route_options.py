"""Route options for POST /paid/lightning/ln-route-options.

DecodePayReq only when a BOLT11 is sent, then one QueryRoutes. Does not pay.
The response lists at most max_routes paths. An empty list is still success.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_BOLT11 = 4096
_MIN_AMOUNT = 100
_MAX_AMOUNT = 50_000
_CAP = 10**15
_HEX = frozenset("0123456789abcdef")
_PREFIXES = (
    ("lnbcrt", "regtest"),
    ("lntbs", "signet"),
    ("lnbc", "bitcoin"),
    ("lntb", "testnet"),
)
_lock = threading.Lock()
_reader: "_Routes | None" = None


class BadInput(Exception):
    """Body, pubkey, amount, or max_routes is unusable."""


class BadInvoice(Exception):
    """Unknown invoice prefix, or DecodePayReq rejected the invoice."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Routes(Protocol):
    """Narrow LND surface. DecodePayReq and QueryRoutes only."""

    def decode_pay_req(self, bolt11: str) -> dict[str, Any]: ...

    def query_routes(self, dest: str, amount_sats: int) -> dict[str, Any]: ...


_ALLOWED = frozenset({"decode_pay_req", "query_routes"})


def _as_dict(msg: Any) -> dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(msg, preserving_proto_field_name=True)


def _object(raw: bytes) -> dict[str, Any]:
    if not raw or not raw.strip():
        raise BadInput("empty body")
    if len(raw) > _MAX_BODY:
        raise BadInput("body too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadInput("invalid json") from exc
    if not isinstance(data, dict):
        raise BadInput("json object required")
    return data


def _uint(value: Any, cap: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        number = int(value)
    else:
        return None
    if number < 0 or number > cap:
        return None
    return number


def _pubkey(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 66 or text[:2] not in ("02", "03"):
        return None
    if any(char not in _HEX for char in text):
        return None
    return text


def _amount(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadInput("amount_sats")
    if value < _MIN_AMOUNT or value > _MAX_AMOUNT:
        raise BadInput("amount_sats")
    return value


def _max_routes(data: dict[str, Any]) -> int:
    if "max_routes" not in data:
        return 3
    value = data["max_routes"]
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadInput("max_routes")
    if value < 1 or value > 3:
        raise BadInput("max_routes")
    return value


def _network(invoice: str) -> str | None:
    """Longest prefix wins so lnbcrt is regtest and lntbs is signet."""
    lowered = invoice.lower()
    for prefix, name in _PREFIXES:
        if lowered.startswith(prefix):
            return name
    return None


def _parse(raw: bytes) -> dict[str, Any]:
    data = _object(raw)
    keys = set(data)
    has_bolt11 = "bolt11" in data
    has_dest = "dest_pubkey" in data
    if has_bolt11 and has_dest:
        raise BadInput("bolt11 and dest_pubkey are mutually exclusive")
    if not has_bolt11 and not has_dest:
        raise BadInput("bolt11 or dest_pubkey required")
    if "amount_sats" not in data:
        raise BadInput("amount_sats required")
    allowed = (
        {"bolt11", "amount_sats", "max_routes"}
        if has_bolt11
        else {"dest_pubkey", "amount_sats", "max_routes"}
    )
    if not keys <= allowed:
        raise BadInput("keys")
    amount = _amount(data["amount_sats"])
    limit = _max_routes(data)
    if has_dest:
        pubkey = _pubkey(data.get("dest_pubkey"))
        if pubkey is None:
            raise BadInput("dest_pubkey")
        return {
            "kind": "dest",
            "dest": pubkey,
            "amount_sats": amount,
            "max_routes": limit,
        }
    invoice = data.get("bolt11")
    if not isinstance(invoice, str) or not invoice.strip():
        raise BadInput("bolt11")
    invoice = invoice.strip()
    if len(invoice) > _MAX_BOLT11:
        raise BadInput("bolt11 too long")
    if _network(invoice) is None:
        raise BadInvoice("bad_invoice")
    return {
        "kind": "bolt11",
        "bolt11": invoice,
        "amount_sats": amount,
        "max_routes": limit,
    }


def _invoice_msat(decoded: dict[str, Any]) -> int:
    if "num_msat" in decoded and decoded["num_msat"] not in (None, ""):
        msat = _uint(decoded["num_msat"], _CAP)
        if msat is None:
            raise LndUnavailable("decode failed")
        return msat
    if "num_satoshis" in decoded and decoded["num_satoshis"] not in (None, ""):
        sats = _uint(decoded["num_satoshis"], _CAP)
        if sats is None:
            raise LndUnavailable("decode failed")
        msat = sats * 1000
        if msat > _CAP:
            raise LndUnavailable("decode failed")
        return msat
    return 0


def _msat_field(row: dict[str, Any], msat_key: str, sat_key: str) -> int | None:
    if msat_key in row and row[msat_key] not in (None, ""):
        return _uint(row[msat_key], _CAP)
    if sat_key in row and row[sat_key] not in (None, ""):
        sats = _uint(row[sat_key], _CAP)
        if sats is None:
            return None
        msat = sats * 1000
        if msat > _CAP:
            return None
        return msat
    return None


def _prob(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and (
        value != value or value in (float("inf"), float("-inf"))
    ):
        return None
    if value < 0 or value > 1:
        return None
    return float(value)


def _rejected(exc: BaseException) -> bool:
    text = str(exc).lower()
    tokens = ("invalid", "checksum", "bech32", "decode", "payreq", "payment request")
    return any(token in text for token in tokens)


def _is_no_route(exc: BaseException) -> bool:
    text = str(exc).lower()
    tokens = (
        "no_route",
        "no route",
        "unable to find a path",
        "unable to find a route",
        "destination unroutable",
    )
    return any(token in text for token in tokens)


def _one(route: Any) -> dict[str, Any]:
    if not isinstance(route, dict):
        raise LndUnavailable("queryroutes failed")
    fees = _msat_field(route, "total_fees_msat", "total_fees")
    hops = route.get("hops")
    if fees is None or not isinstance(hops, list):
        raise LndUnavailable("queryroutes failed")
    item: dict[str, Any] = {"total_fees_msat": fees, "hop_count": len(hops)}
    if "success_prob" in route:
        prob = _prob(route.get("success_prob"))
        if prob is not None:
            item["success_prob"] = prob
    return item


def _route_list(raw: Any, limit: int) -> dict[str, Any]:
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("queryroutes failed") from exc
    routes = data.get("routes")
    if routes is None:
        routes = []
    if not isinstance(routes, list):
        raise LndUnavailable("queryroutes failed")
    return {"routes": [_one(route) for route in routes[:limit]]}


class _Grpc:
    """lnd-grpc-client wrapper. QueryRoutes is called without num_routes."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def decode_pay_req(self, bolt11: str) -> dict[str, Any]:
        return _as_dict(self._call("decode_pay_req", bolt11))

    def query_routes(self, dest: str, amount_sats: int) -> dict[str, Any]:
        return _as_dict(self._call("query_routes", dest, amount_sats))

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Routes:
    cert = (os.environ.get("LND_TLS_CERT_PATH") or "").strip()
    mac = (os.environ.get("LND_READONLY_MACAROON_PATH") or "").strip()
    host = (os.environ.get("LND_GRPC_HOST") or "").strip()
    port = (os.environ.get("LND_GRPC_PORT") or "10009").strip() or "10009"
    if not host or not cert or not mac:
        raise LndUnavailable("LND gRPC env not set")
    if not os.path.isfile(cert) or not os.path.isfile(mac):
        raise LndUnavailable("readonly macaroon or tls cert missing")
    try:
        from lndgrpc import LNDClient as RawLNDClient
    except ImportError as exc:
        raise LndUnavailable("lnd-grpc-client not installed") from exc
    try:
        raw = RawLNDClient(
            ip_address=f"{host}:{port}",
            cert_filepath=cert,
            macaroon_filepath=mac,
        )
    except Exception as exc:
        raise LndUnavailable("lnd grpc connect failed") from exc
    return _Grpc(raw)


def _get_reader(injected: _Routes | None) -> _Routes:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def _destination(parsed: dict[str, Any], live: _Routes) -> tuple[str, int]:
    if parsed["kind"] == "dest":
        return parsed["dest"], parsed["amount_sats"]
    try:
        decoded = _as_dict(live.decode_pay_req(parsed["bolt11"]))
    except (BadInput, BadInvoice, LndUnavailable):
        raise
    except Exception as exc:
        if _rejected(exc):
            raise BadInvoice("bad_invoice") from exc
        raise LndUnavailable("decode failed") from exc
    dest = _pubkey(decoded.get("destination") or decoded.get("dest"))
    if dest is None:
        raise LndUnavailable("decode failed")
    msat = _invoice_msat(decoded)
    supplied = parsed["amount_sats"]
    if msat == 0:
        return dest, supplied
    if msat != supplied * 1000:
        raise BadInput("amount_sats does not match invoice")
    return dest, supplied


def handle_request(body: bytes, reader: _Routes | None = None) -> dict[str, Any]:
    """Return up to max_routes paths. Raises BadInput, BadInvoice, or LndUnavailable."""
    parsed = _parse(body)
    live = _get_reader(reader)
    dest, amount = _destination(parsed, live)
    try:
        raw = live.query_routes(dest, amount)
    except (BadInput, BadInvoice, LndUnavailable):
        raise
    except Exception as exc:
        if _is_no_route(exc):
            return {"routes": []}
        raise LndUnavailable("queryroutes failed") from exc
    return _route_list(raw, parsed["max_routes"])
