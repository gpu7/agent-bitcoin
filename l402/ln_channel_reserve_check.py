"""Channel reserve check for POST /paid/lightning/ln-channel-reserve-check.

One ListChannels. Does not open, close, or pay. A missing peer is not found.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MIN_AMOUNT = 100
_MAX_AMOUNT = 50_000
_CAP = 10**15
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Channels | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or an unexpected key."""


class BadPubkey(Exception):
    """peer_pubkey is not a compressed pubkey."""


class BadAmount(Exception):
    """amount_sats is not an integer from 100 through 50000."""


class ChannelNotFound(Exception):
    """ListChannels has no row for this peer."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Channels(Protocol):
    """Narrow LND surface. ListChannels only."""

    def list_channels(self) -> dict[str, Any]: ...


_ALLOWED = frozenset({"list_channels"})


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
        raise BadAmount("amount_sats")
    if value < _MIN_AMOUNT or value > _MAX_AMOUNT:
        raise BadAmount("amount_sats")
    return value


def _parse(raw: bytes) -> tuple[str, int]:
    data = _object(raw)
    if set(data) != {"peer_pubkey", "amount_sats"}:
        raise BadInput("keys")
    pubkey = _pubkey(data.get("peer_pubkey"))
    if pubkey is None:
        raise BadPubkey("peer_pubkey")
    return pubkey, _amount(data.get("amount_sats"))


def _balance(row: dict[str, Any], key: str) -> int:
    if key not in row or row[key] in (None, ""):
        raise LndUnavailable("listchannels failed")
    number = _uint(row[key], _CAP)
    if number is None:
        raise LndUnavailable("listchannels failed")
    return number


def _reserve(row: dict[str, Any], key: str) -> int:
    if key not in row or row[key] in (None, ""):
        return 0
    number = _uint(row[key], _CAP)
    if number is None:
        raise LndUnavailable("listchannels failed")
    return number


def _check(row: dict[str, Any], amount: int) -> dict[str, Any]:
    local = _balance(row, "local_balance")
    remote = _balance(row, "remote_balance")
    local_reserve = _reserve(row, "local_chan_reserve_sat")
    remote_reserve = _reserve(row, "remote_chan_reserve_sat")
    active = row.get("active")
    if not isinstance(active, bool):
        raise LndUnavailable("listchannels failed")
    return {
        "sufficient_local": local >= amount + local_reserve,
        "sufficient_remote": remote >= amount + remote_reserve,
        "local_balance": local,
        "remote_balance": remote,
        "local_reserve": local_reserve,
        "remote_reserve": remote_reserve,
        "active": active,
    }


def _match(raw: Any, peer: str, amount: int) -> dict[str, Any]:
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    rows = data.get("channels", [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise LndUnavailable("listchannels failed")
    for row in rows:
        if not isinstance(row, dict):
            raise LndUnavailable("listchannels failed")
        pubkey = _pubkey(row.get("remote_pubkey"))
        if pubkey is None:
            raise LndUnavailable("listchannels failed")
        if pubkey != peer:
            continue
        return _check(row, amount)
    raise ChannelNotFound("channel_not_found")


class _Grpc:
    """lnd-grpc-client wrapper exposing only list_channels."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def list_channels(self) -> dict[str, Any]:
        return _as_dict(self._call("list_channels"))

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Channels:
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


def _get_reader(injected: _Channels | None) -> _Channels:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Channels | None = None) -> dict[str, Any]:
    """Return reserve headroom for one peer. Read-only."""
    peer, amount = _parse(body)
    live = _get_reader(reader)
    try:
        raw = live.list_channels()
    except (BadInput, BadPubkey, BadAmount, ChannelNotFound, LndUnavailable):
        raise
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    return _match(raw, peer, amount)
