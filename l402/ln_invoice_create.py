"""Create one invoice for POST /paid/lightning/ln-invoice-create.

One AddInvoice. The caller cannot set expiry. Does not pay, settle, or unlock.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_TEXT = 128
_MAX_BOLT11 = 4096
_MIN_AMOUNT = 100
_MAX_AMOUNT = 50_000
_EXPIRY_S = 3600
_MAX_EXPIRY = 100_000_000
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Create | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or a non-object."""


class BadAmount(Exception):
    """amount_sats is missing or outside 100 through 50000."""


class BadDescription(Exception):
    """description is not printable ASCII."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Create(Protocol):
    """Narrow LND surface. AddInvoice only."""

    def add_invoice(self, amount_sats: int, memo: str) -> dict[str, Any]: ...


_ALLOWED = frozenset({"add_invoice"})


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


def _request(data: dict[str, Any]) -> tuple[int, str]:
    if "amount_sats" not in data:
        raise BadAmount("amount_sats required")
    raw_amount = data.get("amount_sats")
    if isinstance(raw_amount, bool) or not isinstance(raw_amount, int):
        raise BadAmount("amount_sats must be an integer")
    if raw_amount < _MIN_AMOUNT or raw_amount > _MAX_AMOUNT:
        raise BadAmount("amount_sats out of range")
    memo = ""
    if "description" in data and data["description"] is not None:
        text = data["description"]
        if not isinstance(text, str):
            raise BadDescription("description must be text")
        if any(ord(char) < 0x20 or ord(char) > 0x7E for char in text):
            raise BadDescription("description must be printable ASCII")
        memo = text.strip()[:_MAX_TEXT]
    return raw_amount, memo


def _created(raw: Any) -> dict[str, Any]:
    """payment_request, payment_hash, and expiry. No preimage or payment address."""
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = _as_dict(raw)
        except Exception as exc:
            raise LndUnavailable("addinvoice failed") from exc
    payment_hash = _hash(data.get("payment_hash"))
    if payment_hash is None:
        payment_hash = _hash(data.get("r_hash"))
    request = data.get("payment_request")
    if not isinstance(request, str):
        raise LndUnavailable("addinvoice failed")
    request = request.strip()
    if (
        not request.lower().startswith("ln")
        or len(request) > _MAX_BOLT11
        or any(ord(char) < 0x20 or ord(char) > 0x7E for char in request)
    ):
        raise LndUnavailable("addinvoice failed")
    expiry = _uint(data.get("expiry"), _MAX_EXPIRY)
    if payment_hash is None or expiry is None or expiry < 1:
        raise LndUnavailable("addinvoice failed")
    return {
        "payment_request": request,
        "payment_hash": payment_hash,
        "expiry": expiry,
    }


class _Grpc:
    """lnd-grpc-client wrapper exposing only add_invoice."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def add_invoice(self, amount_sats: int, memo: str) -> dict[str, Any]:
        raw = self._call(
            "add_invoice",
            amount_sats,
            memo=memo,
            expiry=_EXPIRY_S,
        )
        if isinstance(raw, dict):
            data = dict(raw)
        else:
            r_hash = getattr(raw, "r_hash", b"")
            data = {
                "payment_request": getattr(raw, "payment_request", ""),
                "payment_hash": r_hash.hex()
                if isinstance(r_hash, (bytes, bytearray))
                else "",
            }
        if "expiry" not in data:
            data["expiry"] = _EXPIRY_S
        return data

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Create:
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


def _get_reader(injected: _Create | None) -> _Create:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Create | None = None) -> dict[str, Any]:
    """Create one invoice. Does not pay or settle."""
    amount, memo = _request(_object(body))
    live = _get_reader(reader)
    try:
        raw = live.add_invoice(amount, memo)
    except (BadInput, BadAmount, BadDescription, LndUnavailable):
        raise
    except Exception as exc:
        raise LndUnavailable("addinvoice failed") from exc
    return _created(raw)
