"""Payable decision for POST /paid/lightning/ln-pay-check.

DecodePayReq and QueryRoutes only. Does not pay. No route is allow false.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_BOLT11 = 4096
_MIN_AMOUNT = 100
_MAX_AMOUNT = 50_000
_MAX_FEE = 50_000
_CAP = 10**15
_MAX_TIME = 10_000_000_000
_MAX_EXPIRY = 100_000_000
_HEX = frozenset("0123456789abcdef")
_NETWORKS = frozenset({"bitcoin", "testnet", "signet", "regtest"})
_PREFIXES = (
    ("lnbcrt", "regtest"),
    ("lntbs", "signet"),
    ("lnbc", "bitcoin"),
    ("lntb", "testnet"),
)
_REASON_ORDER = (
    "expired",
    "zero_amount",
    "below_floor",
    "above_max",
    "network_mismatch",
    "bad_invoice",
    "no_route",
    "fee_above_max",
)
_lock = threading.Lock()
_reader: "_Check | None" = None


class BadInput(Exception):
    """Body shape, pubkey, amount, or fee cap is unusable."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Check(Protocol):
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


def _bounded(value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadInput("integer required")
    if value < low or value > high:
        raise BadInput("integer out of range")
    return value


def _pubkey(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 66 or text[:2] not in ("02", "03"):
        return None
    if any(char not in _HEX for char in text):
        return None
    return text


def _network_of(invoice: str) -> str | None:
    lowered = invoice.lower()
    for prefix, name in _PREFIXES:
        if lowered.startswith(prefix):
            return name
    return None


def _decision(
    reasons: list[str],
    fee_sats: int | None = None,
    hop_count: int | None = None,
) -> dict[str, Any]:
    ordered = [reason for reason in _REASON_ORDER if reason in reasons]
    return {
        "allow": not ordered,
        "reasons": ordered,
        "fee_sats": fee_sats,
        "hop_count": hop_count,
    }


def _optional_fee(data: dict[str, Any]) -> int | None:
    if "max_fee_sats" not in data:
        return None
    return _bounded(data["max_fee_sats"], 0, _MAX_FEE)


def _parse(raw: bytes) -> dict[str, Any]:
    data = _object(raw)
    keys = set(data)
    has_bolt11 = "bolt11" in data
    has_dest = "dest_pubkey" in data
    if has_bolt11 and has_dest:
        raise BadInput("bolt11 and dest_pubkey are mutually exclusive")
    if has_bolt11:
        allowed = {"bolt11", "amount_sats", "max_fee_sats", "network"}
        if not keys <= allowed:
            raise BadInput("keys")
        invoice = data["bolt11"]
        if not isinstance(invoice, str) or not invoice.strip():
            raise BadInput("bolt11 required")
        invoice = invoice.strip()
        if len(invoice) > _MAX_BOLT11:
            raise BadInput("bolt11 too long")
        network = None
        if "network" in data:
            network = data["network"]
            if not isinstance(network, str) or network not in _NETWORKS:
                raise BadInput("network")
        amount = None
        if "amount_sats" in data:
            amount = _bounded(data["amount_sats"], _MIN_AMOUNT, _MAX_AMOUNT)
        return {
            "kind": "bolt11",
            "bolt11": invoice,
            "amount_sats": amount,
            "max_fee_sats": _optional_fee(data),
            "network": network,
        }
    if has_dest:
        allowed = {"dest_pubkey", "amount_sats", "max_fee_sats"}
        if not keys <= allowed or "amount_sats" not in data:
            raise BadInput("dest form")
        pubkey = _pubkey(data.get("dest_pubkey"))
        if pubkey is None:
            raise BadInput("dest_pubkey must be 33-byte compressed hex")
        return {
            "kind": "dest",
            "dest": pubkey,
            "amount_sats": _bounded(data["amount_sats"], _MIN_AMOUNT, _MAX_AMOUNT),
            "max_fee_sats": _optional_fee(data),
        }
    raise BadInput("bolt11 or dest_pubkey required")


def _invoice_sats(decoded: dict[str, Any]) -> int:
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


def _expired(decoded: dict[str, Any], now: int) -> bool:
    if "timestamp" not in decoded or "expiry" not in decoded:
        raise LndUnavailable("decode failed")
    created = _uint(decoded["timestamp"], _MAX_TIME)
    expiry = _uint(decoded["expiry"], _MAX_EXPIRY)
    if created is None or expiry is None:
        raise LndUnavailable("decode failed")
    return created + expiry <= now


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


def _fee_decision(fee_sats: int, hop_count: int, max_fee: int | None) -> dict[str, Any]:
    reasons: list[str] = []
    if max_fee is not None and fee_sats > max_fee:
        reasons.append("fee_above_max")
    return _decision(reasons, fee_sats, hop_count)


def _from_route(raw: Any, max_fee: int | None) -> dict[str, Any]:
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("queryroutes failed") from exc
    routes = data.get("routes")
    if routes in (None, []):
        return _decision(["no_route"])
    if not isinstance(routes, list) or not isinstance(routes[0], dict):
        raise LndUnavailable("queryroutes failed")
    first = routes[0]
    hops = first.get("hops")
    if not isinstance(hops, list):
        raise LndUnavailable("queryroutes failed")
    if len(hops) < 1:
        return _decision(["no_route"])
    fees = _msat_field(first, "total_fees_msat", "total_fees")
    if fees is None:
        raise LndUnavailable("queryroutes failed")
    return _fee_decision((fees + 999) // 1000, len(hops), max_fee)


def _amount_reasons(sats: int) -> list[str]:
    if sats == 0:
        return ["zero_amount"]
    if sats < _MIN_AMOUNT:
        return ["below_floor"]
    if sats > _MAX_AMOUNT:
        return ["above_max"]
    return []


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


def connect() -> _Check:
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


def _get_reader(injected: _Check | None) -> _Check:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def _query(live: _Check, dest: str, amount: int, max_fee: int | None) -> dict[str, Any]:
    try:
        raw = live.query_routes(dest, amount)
    except LndUnavailable:
        raise
    except Exception as exc:
        if _is_no_route(exc):
            return _decision(["no_route"])
        raise LndUnavailable("queryroutes failed") from exc
    return _from_route(raw, max_fee)


def _from_invoice(live: _Check, parsed: dict[str, Any], now: int) -> dict[str, Any]:
    try:
        decoded = _as_dict(live.decode_pay_req(parsed["bolt11"]))
    except LndUnavailable:
        raise
    except Exception as exc:
        if _rejected(exc):
            return _decision(["bad_invoice"])
        raise LndUnavailable("decode failed") from exc
    reasons: list[str] = []
    if _expired(decoded, now):
        reasons.append("expired")
    sats = _invoice_sats(decoded)
    provided = parsed["amount_sats"]
    if provided is not None and provided != sats:
        raise BadInput("amount_sats does not match invoice")
    reasons.extend(_amount_reasons(sats))
    if reasons:
        return _decision(reasons)
    dest = _pubkey(decoded.get("destination") or decoded.get("dest"))
    if dest is None:
        raise LndUnavailable("decode failed")
    return _query(live, dest, sats, parsed["max_fee_sats"])


def handle_request(
    body: bytes, reader: _Check | None = None, now: int | None = None
) -> dict[str, Any]:
    """Decide one payment. Raises BadInput or LndUnavailable."""
    parsed = _parse(body)
    if parsed["kind"] == "bolt11":
        network = _network_of(parsed["bolt11"])
        if network is None:
            return _decision(["bad_invoice"])
        expected = parsed.get("network")
        if expected is not None and expected != network:
            return _decision(["network_mismatch"])
    live = _get_reader(reader)
    if parsed["kind"] == "dest":
        return _query(
            live, parsed["dest"], parsed["amount_sats"], parsed["max_fee_sats"]
        )
    clock = int(time.time()) if now is None else now
    return _from_invoice(live, parsed, clock)
