"""Read-only route estimate for POST /paid/lightning/ln-path-estimate.

DecodePayReq only when a BOLT11 is sent, then QueryRoutes. Does not pay.
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
_MAX_HOPS = 8
_CAP = 10**15
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Routes | None" = None


class BadInput(Exception):
    """Body, pubkey, amount, or invoice shape is unusable."""


class NoRoute(Exception):
    """QueryRoutes found no path."""


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


def _short_pubkey(pubkey: str) -> str:
    return f"{pubkey[:8]}…{pubkey[-4:]}"


def _amount(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadInput("amount_sats must be an integer")
    if value < _MIN_AMOUNT or value > _MAX_AMOUNT:
        raise BadInput("amount_sats out of range")
    return value


def parse_body(raw: bytes) -> dict[str, Any]:
    """Validate XOR input before any RPC. Does not echo bolt11."""
    data = _object(raw)
    bolt11 = data.get("bolt11")
    dest = data.get("dest_pubkey")
    has_bolt11 = isinstance(bolt11, str) and bool(bolt11.strip())
    has_dest = isinstance(dest, str) and bool(dest.strip())
    if ("bolt11" in data and not has_bolt11) or (
        "dest_pubkey" in data and not has_dest
    ):
        raise BadInput("bolt11 or dest_pubkey required")
    if has_bolt11 and has_dest:
        raise BadInput("bolt11 and dest_pubkey are mutually exclusive")
    if not has_bolt11 and not has_dest:
        raise BadInput("bolt11 or dest_pubkey required")
    amount = _amount(data.get("amount_sats")) if "amount_sats" in data else None
    if has_dest:
        pubkey = _pubkey(dest)
        if pubkey is None:
            raise BadInput("dest_pubkey must be 33-byte compressed hex")
        if amount is None:
            raise BadInput("amount_sats required with dest_pubkey")
        return {"kind": "dest", "dest": pubkey, "amount_sats": amount}
    invoice = str(bolt11).strip()
    if not invoice.lower().startswith("ln") or len(invoice) > _MAX_BOLT11:
        raise BadInput("bolt11 must be a Lightning invoice")
    return {"kind": "bolt11", "bolt11": invoice, "amount_sats": amount}


def _invoice_amount_sats(decoded: dict[str, Any]) -> int:
    if "num_msat" in decoded and decoded["num_msat"] not in (None, ""):
        msat = _uint(decoded["num_msat"], _CAP)
        if msat is None:
            raise LndUnavailable("decode failed")
        return msat // 1000
    if "num_satoshis" in decoded and decoded["num_satoshis"] not in (None, ""):
        sats = _uint(decoded["num_satoshis"], _CAP)
        if sats is None:
            raise LndUnavailable("decode failed")
        return sats
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


def estimate(raw: Any) -> dict[str, Any]:
    """First route only. Short hop pubkeys. No channel ids and no bolt11."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("queryroutes failed") from exc
    routes = data.get("routes")
    if routes in (None, []):
        raise NoRoute("no_route")
    if not isinstance(routes, list):
        raise LndUnavailable("queryroutes failed")
    first = routes[0]
    if not isinstance(first, dict):
        raise LndUnavailable("queryroutes failed")
    hops = first.get("hops") or []
    if not isinstance(hops, list) or len(hops) < 1:
        raise NoRoute("no_route")
    fees = _msat_field(first, "total_fees_msat", "total_fees")
    total = _msat_field(first, "total_amt_msat", "total_amt")
    if fees is None or total is None:
        raise LndUnavailable("queryroutes failed")
    short: list[str] = []
    for hop in hops:
        if not isinstance(hop, dict):
            raise LndUnavailable("queryroutes failed")
        pubkey = _pubkey(hop.get("pub_key", hop.get("pubkey")))
        if pubkey is None:
            raise LndUnavailable("queryroutes failed")
        short.append(_short_pubkey(pubkey))
    out: dict[str, Any] = {
        "total_fees_msat": fees,
        "total_amt_msat": total,
        "hop_count": len(hops),
        "hops": short[:_MAX_HOPS],
    }
    if len(short) > _MAX_HOPS:
        out["truncated"] = True
    source = (
        data if "success_prob" in data else first if "success_prob" in first else None
    )
    if source is not None:
        prob = _prob(source.get("success_prob"))
        if prob is None:
            raise LndUnavailable("queryroutes failed")
        out["success_prob"] = prob
    return out


class _Grpc:
    """lnd-grpc-client wrapper exposing only decode_pay_req and query_routes."""

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
    except (BadInput, NoRoute, LndUnavailable):
        raise
    except Exception as exc:
        if _rejected(exc):
            raise BadInput("invoice parse failed") from exc
        raise LndUnavailable("decode failed") from exc
    dest = _pubkey(decoded.get("destination") or decoded.get("dest"))
    if dest is None:
        raise BadInput("invoice dest missing")
    invoice_amount = _invoice_amount_sats(decoded)
    provided = parsed.get("amount_sats")
    if invoice_amount <= 0:
        if provided is None:
            raise BadInput("zero-amount invoice requires amount_sats")
        amount = provided
    elif provided is not None and provided != invoice_amount:
        raise BadInput("amount_sats does not match invoice")
    else:
        amount = invoice_amount
        if amount < _MIN_AMOUNT or amount > _MAX_AMOUNT:
            raise BadInput("invoice amount out of range")
    return dest, amount


def handle_request(body: bytes, reader: _Routes | None = None) -> dict[str, Any]:
    """Estimate one route. Raises BadInput, NoRoute, or LndUnavailable."""
    parsed = parse_body(body)
    live = _get_reader(reader)
    dest, amount = _destination(parsed, live)
    try:
        raw = live.query_routes(dest, amount)
    except NoRoute:
        raise
    except LndUnavailable:
        raise
    except Exception as exc:
        if _is_no_route(exc):
            raise NoRoute("no_route") from exc
        raise LndUnavailable("queryroutes failed") from exc
    return estimate(raw)
