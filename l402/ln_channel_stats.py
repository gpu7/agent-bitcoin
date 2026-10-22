"""Read-only channel summary for GET /paid/lightning/ln-channel-stats.

ListChannels only. Does not unlock, open, close, or pay.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Protocol

_MAX_LISTED = 8
_MAX_ALIAS = 32
_lock = threading.Lock()
_reader: "_Channels | None" = None


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Channels(Protocol):
    """Narrow LND surface. Must not include spend or channel-mutation RPCs."""

    def list_channels(self) -> dict[str, Any]: ...


def _as_dict(msg: Any) -> dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(msg, preserving_proto_field_name=True)


def _active(value: Any) -> bool | None:
    """Protobuf omits false. Any other type is unreadable."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return None


def _sats(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        amount = int(value)
    else:
        return None
    if amount < 0:
        return None
    return amount


def _channel_point(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    txid, sep, index = value.strip().lower().partition(":")
    if sep != ":" or len(txid) != 64 or not index.isdigit() or len(index) > 6:
        return None
    if any(char not in "0123456789abcdef" for char in txid):
        return None
    return f"{txid}:{int(index)}"


def _alias(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = "".join(char for char in value.strip() if char.isprintable())
    text = text[:_MAX_ALIAS]
    return text or None


def summarize(raw: Any) -> dict[str, Any]:
    """Totals cover every channel. The list is active channels only."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    rows = data.get("channels", [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise LndUnavailable("listchannels failed")
    num_active = 0
    num_inactive = 0
    capacity = 0
    local = 0
    remote = 0
    listed: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise LndUnavailable("listchannels failed")
        flag = _active(row.get("active"))
        if flag is None:
            raise LndUnavailable("listchannels failed")
        cap = _sats(row.get("capacity"))
        loc = _sats(row.get("local_balance"))
        rem = _sats(row.get("remote_balance"))
        if cap is None or loc is None or rem is None:
            raise LndUnavailable("listchannels failed")
        if flag:
            num_active += 1
        else:
            num_inactive += 1
        capacity += cap
        local += loc
        remote += rem
        if not flag or len(listed) >= _MAX_LISTED:
            continue
        item: dict[str, str] = {}
        point = _channel_point(row.get("channel_point"))
        alias = _alias(row.get("peer_alias"))
        if point:
            item["channel_point"] = point
        if alias:
            item["peer_alias"] = alias
        if item:
            listed.append(item)
    return {
        "num_active": num_active,
        "num_inactive": num_inactive,
        "total_capacity_sats": capacity,
        "total_local_balance_sats": local,
        "total_remote_balance_sats": remote,
        "channels": listed,
    }


class _GrpcChannels:
    """lnd-grpc-client wrapper exposing only list_channels."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def list_channels(self) -> dict[str, Any]:
        return _as_dict(self._raw.list_channels())


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
    return _GrpcChannels(raw)


def _get_reader(injected: _Channels | None) -> _Channels:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(reader: _Channels | None = None) -> dict[str, Any]:
    """Return the summary. Raises LndUnavailable. Never returns raw channels."""
    live = _get_reader(reader)
    try:
        raw = live.list_channels()
    except LndUnavailable:
        raise
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    return summarize(raw)
