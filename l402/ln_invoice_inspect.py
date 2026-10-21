"""Read-only BOLT11 inspect for POST /paid/lightning/ln-invoice-inspect.

One DecodePayReq. Does not pay, settle, or unlock.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_BOLT11 = 4096
_MAX_TEXT = 128
_MAX_EXPIRY = 100_000_000
_MAX_CLTV = 1_000_000
_MAX_FEATURES = 8
_CAP = 10**15
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Decode | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or a non-object."""


class BadInvoice(Exception):
    """BOLT11 missing, malformed, or rejected by DecodePayReq."""


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


def _ascii(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in value):
        return None
    return value.strip()[:limit]


def _bolt11(data: dict[str, Any]) -> str:
    raw = data.get("bolt11")
    if not isinstance(raw, str):
        raise BadInvoice("bolt11 required")
    text = raw.strip()
    if not text.lower().startswith("ln") or len(text) > _MAX_BOLT11:
        raise BadInvoice("bolt11 required")
    return text


def _amount_msat(data: dict[str, Any]) -> int | None:
    if "num_msat" in data and data["num_msat"] not in (None, ""):
        return _uint(data["num_msat"], _CAP)
    if "num_satoshis" in data and data["num_satoshis"] not in (None, ""):
        sats = _uint(data["num_satoshis"], _CAP)
        if sats is None:
            return None
        msat = sats * 1000
        if msat > _CAP:
            return None
        return msat
    return None


def _feature_bits(value: Any) -> list[int] | None:
    bits: list[int] = []
    items: list[Any]
    if isinstance(value, dict):
        items = list(value.keys())
    elif isinstance(value, list):
        items = []
        for item in value:
            if isinstance(item, dict):
                if "bit" in item:
                    items.append(item.get("bit"))
                elif "feature_bit" in item:
                    items.append(item.get("feature_bit"))
                else:
                    return None
            else:
                items.append(item)
    else:
        return None
    for item in items:
        bit = _uint(item, 1_000_000)
        if bit is None:
            return None
        bits.append(bit)
    return bits


def _rejected(exc: BaseException) -> bool:
    text = str(exc).lower()
    tokens = ("invalid", "checksum", "bech32", "decode", "payreq", "payment request")
    return any(token in text for token in tokens)


def inspect_invoice(raw: Any) -> dict[str, Any]:
    """Public decode fields. Drops the bolt11, route hints, and preimage."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("decode failed") from exc
    amount = _amount_msat(data)
    expiry = _uint(data.get("expiry"), _MAX_EXPIRY)
    payment_hash = _hash(data.get("payment_hash"))
    cltv = _uint(data.get("cltv_expiry"), _MAX_CLTV)
    if amount is None or expiry is None or payment_hash is None or cltv is None:
        raise LndUnavailable("decode failed")
    out: dict[str, Any] = {
        "amount_msat": amount,
        "expiry": expiry,
        "payment_hash": payment_hash,
        "cltv_expiry": cltv,
    }
    if "description" in data and data["description"] not in (None, ""):
        memo = _ascii(data["description"], _MAX_TEXT)
        if memo is None:
            raise LndUnavailable("decode failed")
        if memo:
            out["description"] = memo
    elif "memo" in data and data["memo"] not in (None, ""):
        memo = _ascii(data["memo"], _MAX_TEXT)
        if memo is None:
            raise LndUnavailable("decode failed")
        if memo:
            out["description"] = memo
    dest_raw = data.get("destination", data.get("dest"))
    if dest_raw not in (None, ""):
        dest = _pubkey(dest_raw)
        if dest is None:
            raise LndUnavailable("decode failed")
        out["destination"] = _short_pubkey(dest)
    if "features" in data and data["features"] not in (None, "", [], {}):
        bits = _feature_bits(data["features"])
        if bits is None:
            raise LndUnavailable("decode failed")
        if bits:
            out["features"] = bits[:_MAX_FEATURES]
            if len(bits) > _MAX_FEATURES:
                out["truncated"] = True
    return out


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
    """Decode one invoice. Raises BadInput, BadInvoice, or LndUnavailable."""
    invoice = _bolt11(_object(body))
    live = _get_reader(reader)
    try:
        raw = live.decode_pay_req(invoice)
    except (BadInput, BadInvoice, LndUnavailable):
        raise
    except Exception as exc:
        if _rejected(exc):
            raise BadInvoice("invoice parse failed") from exc
        raise LndUnavailable("decode failed") from exc
    return inspect_invoice(raw)
