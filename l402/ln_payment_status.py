"""Read-only invoice status for POST /paid/lightning/ln-payment-status.

One LookupInvoice for an invoice this node created. Does not list payments or pay.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_TEXT = 128
_MAX_DATE = 10_000_000_000
_CAP = 10**15
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Invoice | None" = None
_STATUS = {
    "OPEN": "pending",
    "ACCEPTED": "pending",
    "SETTLED": "succeeded",
    "CANCELED": "failed",
    "CANCELLED": "failed",
}
_STATUS_INT = {0: "pending", 1: "succeeded", 2: "failed", 3: "pending"}


class BadInput(Exception):
    """Missing body, bad JSON, or a non-object."""


class BadPaymentHash(Exception):
    """payment_hash is missing or not 64 hex characters."""


class PaymentNotFound(Exception):
    """This node has no invoice for that payment hash."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Invoice(Protocol):
    """Narrow LND surface. LookupInvoice only."""

    def lookup_invoice(self, payment_hash: str) -> dict[str, Any]: ...


_ALLOWED = frozenset({"lookup_invoice"})


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


def _hash(value: Any) -> str | None:
    if isinstance(value, (bytes, bytearray)):
        if len(value) != 32:
            return None
        value = value.hex()
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 64 or any(char not in _HEX for char in text):
        return None
    return text


def _ascii(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        return None
    return value.strip()[:limit]


def _payment_hash(data: dict[str, Any]) -> str:
    if set(data) != {"payment_hash"}:
        raise BadPaymentHash("payment_hash required")
    parsed = _hash(data.get("payment_hash"))
    if parsed is None:
        raise BadPaymentHash("payment_hash required")
    return parsed


def _status(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _STATUS_INT.get(value)
    if not isinstance(value, str):
        return None
    return _STATUS.get(value.strip().upper())


def _value_msat(data: dict[str, Any]) -> int | None:
    if "value_msat" in data and data["value_msat"] not in (None, ""):
        return _uint(data["value_msat"], _CAP)
    if "value" in data and data["value"] not in (None, ""):
        sats = _uint(data["value"], _CAP)
        if sats is None:
            return None
        msat = sats * 1000
        if msat > _CAP:
            return None
        return msat
    return None


def _unknown(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "not found" in text or "unable to locate" in text


def payment_status(raw: Any) -> dict[str, Any]:
    """Invoice state only. Drops the preimage, payment request, and memo."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("lookupinvoice failed") from exc
    status = _status(data.get("state"))
    value = _value_msat(data)
    created = _uint(data.get("creation_date"), _MAX_DATE)
    if status is None or value is None or created is None:
        raise LndUnavailable("lookupinvoice failed")
    out: dict[str, Any] = {
        "status": status,
        "value_msat": value,
        "creation_date": created,
    }
    if "failure_reason" in data and data["failure_reason"] not in (None, ""):
        reason = _ascii(data["failure_reason"], _MAX_TEXT)
        if reason is None:
            raise LndUnavailable("lookupinvoice failed")
        if reason:
            out["failure_reason"] = reason
    return out


class _Grpc:
    """lnd-grpc-client wrapper exposing only lookup_invoice."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def lookup_invoice(self, payment_hash: str) -> dict[str, Any]:
        return _as_dict(self._call("lookup_invoice", payment_hash))

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Invoice:
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


def _get_reader(injected: _Invoice | None) -> _Invoice:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Invoice | None = None) -> dict[str, Any]:
    """Look up one created invoice. Does not call list_payments."""
    payment_hash = _payment_hash(_object(body))
    live = _get_reader(reader)
    try:
        raw = live.lookup_invoice(payment_hash)
    except (BadInput, BadPaymentHash, PaymentNotFound, LndUnavailable):
        raise
    except Exception as exc:
        if _unknown(exc):
            raise PaymentNotFound("payment not found") from exc
        raise LndUnavailable("lookupinvoice failed") from exc
    return payment_status(raw)
