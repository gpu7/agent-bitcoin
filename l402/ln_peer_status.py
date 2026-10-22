"""Read-only peer status for POST /paid/lightning/ln-peer-status.

ListPeers, then ListChannels. Does not connect, disconnect, or pay.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_LISTED = 8
_MAX_COUNT = 100_000
_MAX_PING_MS = 3_600_000
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Peers | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or a non-object."""


class BadPubkey(Exception):
    """peer_pubkey is present and not a compressed pubkey."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Peers(Protocol):
    """Narrow LND surface. ListPeers and ListChannels only."""

    def list_peers(self) -> dict[str, Any]: ...

    def list_channels(self) -> dict[str, Any]: ...


_ALLOWED = frozenset({"list_peers", "list_channels"})


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


def _active(value: Any) -> bool | None:
    """Protobuf omits false. Any other type is unreadable."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return None


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


def _ping_ms(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    millis = value // 1_000_000
    if millis > _MAX_PING_MS:
        return _MAX_PING_MS
    return millis


def _rows(value: Any, key: str) -> list[Any]:
    if not isinstance(value, dict):
        raise LndUnavailable("peer status failed")
    rows = value.get(key, [])
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise LndUnavailable("peer status failed")
    return rows


def _channel_counts(raw: Any) -> dict[str, tuple[int, int]]:
    counts: dict[str, tuple[int, int]] = {}
    for row in _rows(raw, "channels"):
        if not isinstance(row, dict):
            raise LndUnavailable("listchannels failed")
        pubkey = _pubkey(row.get("remote_pubkey"))
        active = _active(row.get("active"))
        if pubkey is None or active is None:
            raise LndUnavailable("listchannels failed")
        num, active_num = counts.get(pubkey, (0, 0))
        num += 1
        if active:
            active_num += 1
        if num > _MAX_COUNT or active_num > _MAX_COUNT:
            raise LndUnavailable("listchannels failed")
        counts[pubkey] = (num, active_num)
    return counts


def _peer_row(
    pubkey: str, connected: bool, counts: dict[str, tuple[int, int]], peer: Any
) -> dict[str, Any]:
    num, active_num = counts.get(pubkey, (0, 0))
    row: dict[str, Any] = {
        "remote_pubkey": _short_pubkey(pubkey),
        "connected": connected,
        "num_channels": num,
        "active_channels": active_num,
    }
    if connected and isinstance(peer, dict) and "ping_time" in peer:
        ping = _ping_ms(peer.get("ping_time"))
        if ping is not None:
            row["last_ping_ms"] = ping
    return row


def peer_status(peers_raw: Any, channels_raw: Any, peer: str | None) -> dict[str, Any]:
    """Connected peers, or one filtered row when a pubkey is requested."""
    try:
        counts = _channel_counts(_as_dict(channels_raw))
        peers = _rows(_as_dict(peers_raw), "peers")
    except LndUnavailable:
        raise
    except Exception as exc:
        raise LndUnavailable("peer status failed") from exc
    if peer is not None:
        found: Any = None
        for item in peers:
            if not isinstance(item, dict):
                raise LndUnavailable("listpeers failed")
            pubkey = _pubkey(item.get("pub_key", item.get("pubkey")))
            if pubkey is None:
                raise LndUnavailable("listpeers failed")
            if pubkey == peer:
                found = item
        return {"peers": [_peer_row(peer, found is not None, counts, found)]}
    listed: list[dict[str, Any]] = []
    extra = False
    for item in peers:
        if not isinstance(item, dict):
            raise LndUnavailable("listpeers failed")
        pubkey = _pubkey(item.get("pub_key", item.get("pubkey")))
        if pubkey is None:
            raise LndUnavailable("listpeers failed")
        if len(listed) >= _MAX_LISTED:
            extra = True
            continue
        listed.append(_peer_row(pubkey, True, counts, item))
    out: dict[str, Any] = {"peers": listed}
    if extra:
        out["truncated"] = True
    return out


class _Grpc:
    """lnd-grpc-client wrapper exposing only list_peers and list_channels."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def list_peers(self) -> dict[str, Any]:
        return _as_dict(self._call("list_peers"))

    def list_channels(self) -> dict[str, Any]:
        return _as_dict(self._call("list_channels"))

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Peers:
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


def _get_reader(injected: _Peers | None) -> _Peers:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Peers | None = None) -> dict[str, Any]:
    """Return peer status. ListChannels runs only after ListPeers succeeds."""
    peer = _peer_filter(_object(body))
    live = _get_reader(reader)
    try:
        peers_raw = live.list_peers()
    except (BadInput, BadPubkey, LndUnavailable):
        raise
    except Exception as exc:
        raise LndUnavailable("listpeers failed") from exc
    try:
        channels_raw = live.list_channels()
    except (BadInput, BadPubkey, LndUnavailable):
        raise
    except Exception as exc:
        raise LndUnavailable("listchannels failed") from exc
    return peer_status(peers_raw, channels_raw, peer)
