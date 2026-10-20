"""Read-only node card for GET /paid/lightning/ln-node-info.

GetInfo only. Does not unlock, open, close, or pay.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Protocol

_MAX_ALIAS = 32
_MAX_VERSION = 64
_MAX_COUNT = 100_000
_MAX_HEIGHT = 10_000_000
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Info | None" = None


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Info(Protocol):
    """Narrow LND surface. Must not include spend or channel-mutation RPCs."""

    def get_info(self) -> dict[str, Any]: ...


def _as_dict(msg: Any) -> dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(msg, preserving_proto_field_name=True)


def _ascii_text(value: Any, limit: int, *, allow_empty: bool) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in text):
        return None
    text = text[:limit]
    if not text and not allow_empty:
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


def _count(value: Any, cap: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        amount = int(value)
    else:
        return None
    if amount < 0 or amount > cap:
        return None
    return amount


def node_info(raw: Any) -> dict[str, Any]:
    """Seven public fields. Drops URIs, color, and the commit hash."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("getinfo failed") from exc
    alias = _ascii_text(data.get("alias"), _MAX_ALIAS, allow_empty=True)
    pubkey = _pubkey(data.get("identity_pubkey"))
    active = _count(data.get("num_active_channels"), _MAX_COUNT)
    peers = _count(data.get("num_peers"), _MAX_COUNT)
    height = _count(data.get("block_height"), _MAX_HEIGHT)
    synced = data.get("synced_to_chain")
    version = _ascii_text(data.get("version"), _MAX_VERSION, allow_empty=False)
    if (
        alias is None
        or pubkey is None
        or active is None
        or peers is None
        or height is None
        or not isinstance(synced, bool)
        or version is None
    ):
        raise LndUnavailable("getinfo failed")
    return {
        "alias": alias,
        "identity_pubkey": pubkey,
        "num_active_channels": active,
        "num_peers": peers,
        "block_height": height,
        "synced_to_chain": synced,
        "version": version,
    }


class _GrpcInfo:
    """lnd-grpc-client wrapper exposing only get_info."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get_info(self) -> dict[str, Any]:
        return _as_dict(self._raw.get_info())


def connect() -> _Info:
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
    return _GrpcInfo(raw)


def _get_reader(injected: _Info | None) -> _Info:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(reader: _Info | None = None) -> dict[str, Any]:
    """Return the node card. Raises LndUnavailable. Never returns raw GetInfo."""
    live = _get_reader(reader)
    try:
        raw = live.get_info()
    except LndUnavailable:
        raise
    except Exception as exc:
        raise LndUnavailable("getinfo failed") from exc
    return node_info(raw)
