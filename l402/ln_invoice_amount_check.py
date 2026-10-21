"""Invoice amount check for POST /paid/lightning/ln-invoice-amount-check.

One DecodePayReq. Reports open versus fixed amounts. Does not look up a route.
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
_lock = threading.Lock()
_reader: "_Decode | None" = None


class BadInput(Exception):
    """Body shape or supplied amount is unusable."""


class BadInvoice(Exception):
    """DecodePayReq rejected the invoice."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Decode(Protocol):
    """Narrow LND surface. DecodePayReq only."""

    def decode_pay_req(self, bolt11: str) -> dict[str, Any]: ...


_ALLOWED = frozenset({"decode_pay_req"})


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


def _supplied(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadInput("amount_sats")
    if value < 0 or value > _MAX_AMOUNT:
        raise BadInput("amount_sats")
    return value


def _parse(raw: bytes) -> tuple[str, int | None]:
    data = _object(raw)
    if not set(data) <= {"bolt11", "amount_sats"} or "bolt11" not in data:
        raise BadInput("keys")
    invoice = data["bolt11"]
    if not isinstance(invoice, str) or not invoice.strip():
        raise BadInput("bolt11")
    invoice = invoice.strip()
    if len(invoice) > _MAX_BOLT11:
        raise BadInput("bolt11 too long")
    amount = _supplied(data["amount_sats"]) if "amount_sats" in data else None
    return invoice, amount


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


def _open_bounds(supplied: int | None) -> tuple[bool, str]:
    if supplied is None:
        return False, "amount_required"
    if supplied < _MIN_AMOUNT:
        return False, "below_floor"
    if supplied > _MAX_AMOUNT:
        return False, "above_max"
    return True, ""


def _fixed_bounds(msat: int, supplied: int | None) -> tuple[bool, str]:
    if supplied is not None and msat != supplied * 1000:
        return False, "amount_mismatch"
    sats = msat // 1000
    if sats < _MIN_AMOUNT:
        return False, "below_floor"
    if sats > _MAX_AMOUNT:
        return False, "above_max"
    return True, ""


def _result(msat: int, supplied: int | None) -> dict[str, Any]:
    amount_less = msat == 0
    within, reason = (
        _open_bounds(supplied) if amount_less else _fixed_bounds(msat, supplied)
    )
    return {
        "amount_less": amount_less,
        "amount_msat": msat,
        "supplied_amount_sats": supplied,
        "within_bounds": within,
        "reason": reason,
    }


def _rejected(exc: BaseException) -> bool:
    text = str(exc).lower()
    tokens = ("invalid", "checksum", "bech32", "decode", "payreq", "payment request")
    return any(token in text for token in tokens)


class _Grpc:
    """lnd-grpc-client wrapper exposing only decode_pay_req."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def decode_pay_req(self, bolt11: str) -> dict[str, Any]:
        return _as_dict(self._call("decode_pay_req", bolt11))

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Decode:
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


def _get_reader(injected: _Decode | None) -> _Decode:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Decode | None = None) -> dict[str, Any]:
    """Return the amount check. Raises BadInput, BadInvoice, or LndUnavailable."""
    invoice, supplied = _parse(body)
    live = _get_reader(reader)
    try:
        decoded = _as_dict(live.decode_pay_req(invoice))
    except (BadInput, BadInvoice, LndUnavailable):
        raise
    except Exception as exc:
        if _rejected(exc):
            raise BadInvoice("bad_invoice") from exc
        raise LndUnavailable("decode failed") from exc
    return _result(_invoice_msat(decoded), supplied)
