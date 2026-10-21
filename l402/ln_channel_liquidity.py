"""Read-only channel balances for POST /paid/lightning/ln-channel-liquidity.

One ListChannels. Does not open, close, or pay.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_LISTED = 8
_CAP = 10**15
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Channels | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or a non-object."""


class BadPubkey(Exception):
    """peer_pubkey is present and not a compressed pubkey."""


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


def _short_pubkey(pubkey: str) -> str:
    return f"{pubkey[:8]}…{pubkey[-4:]}"


def _peer_filter(data: dict[str, Any]) -> str | None:
    if "peer_pubkey" not in data:
        return None
    pubkey = _pubkey(data.get("peer_pubkey"))
    if pubkey is None:
        raise BadPubkey("peer_pubkey invalid")
    return pubkey


def _row(row: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(row, dict):
        raise LndUnavailable("listchannels failed")
    pubkey = _pubkey(row.get("remote_pubkey"))
    capacity = _uint(row.get("capacity"), _CAP)
    local = _uint(row.get("local_balance"), _CAP)
    remote = _uint(row.get("remote_balance"), _CAP)
    active = row.get("active")
    if (
        pubkey is None
        or capacity is None
        or local is None
        or remote is None
        or not isinstance(active, bool)
    ):
        raise LndUnavailable("listchannels failed")
    return pubkey, {
        "remote_pubkey": _short_pubkey(pubkey),
        "capacity": capacity,
        "local_balance": local,
        "remote_balance": remote,
        "active": active,
    }


def liquidity(raw: Any, peer: str | None) -> dict[str, Any]:
    """At most eight rows. No channel points, HTLCs, or addresses."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    rows = data.get("channels", [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise LndUnavailable("listchannels failed")
    matched: list[dict[str, Any]] = []
    for row in rows:
        pubkey, item = _row(row)
        if peer is not None and pubkey != peer:
            continue
        matched.append(item)
    out: dict[str, Any] = {"channels": matched[:_MAX_LISTED]}
    if len(matched) > _MAX_LISTED:
        out["truncated"] = True
    return out


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
    """Return channel balances. Raises BadInput, BadPubkey, or LndUnavailable."""
    peer = _peer_filter(_object(body))
    live = _get_reader(reader)
    try:
        raw = live.list_channels()
    except (BadInput, BadPubkey, LndUnavailable):
        raise
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    return liquidity(raw, peer)
