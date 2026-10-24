"""Public graph card for POST /paid/lightning/ln-node-card.

One GetNodeInfo with include_channels false. Does not return the pubkey.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_CAP = 10**15
_MAX_ALIAS = 32
_MAX_CHANNELS = 1_000_000
_MAX_TIME = 10_000_000_000
_MAX_ADDRESSES = 4
_MAX_HOST = 64
_HEX = frozenset("0123456789abcdef")
_lock = threading.Lock()
_reader: "_Card | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or an unexpected key."""


class BadPubkey(Exception):
    """pubkey is not 33-byte compressed hex."""


class NodeNotFound(Exception):
    """GetNodeInfo does not know this pubkey."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Card(Protocol):
    """Narrow LND surface. GetNodeInfo only."""

    def get_node_info(
        self, pub_key: str, include_channels: bool = False
    ) -> dict[str, Any]: ...


_ALLOWED = frozenset({"get_node_info"})


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


def _printable(value: str) -> bool:
    return all(32 <= ord(char) <= 126 for char in value)


def _alias(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _printable(text):
        return None
    return text[:_MAX_ALIAS]


def _host(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("addr")
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or not _printable(text):
        return None
    host, sep, port = text.rpartition(":")
    if sep and port.isdigit() and host:
        text = host
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    text = text.strip()
    if not text or not _printable(text):
        return None
    return text[:_MAX_HOST]


def _addresses(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], False
    if not isinstance(value, list):
        raise LndUnavailable("getnodeinfo failed")
    hosts: list[str] = []
    for item in value[:_MAX_ADDRESSES]:
        host = _host(item)
        if host is not None:
            hosts.append(host)
    return hosts, len(value) > _MAX_ADDRESSES


def _missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    code = ""
    get_code = getattr(exc, "code", None)
    if callable(get_code):
        try:
            code = str(getattr(get_code(), "name", "") or "")
        except Exception:
            code = ""
    if code == "NOT_FOUND" or "not_found" in text:
        return True
    return "unable to find" in text or "not found" in text


def _classify(exc: BaseException) -> None:
    """NOT_FOUND is an unknown node. Every other RPC error is unavailable."""
    if _missing(exc):
        raise NodeNotFound("node_not_found") from exc
    raise LndUnavailable("getnodeinfo failed") from exc


def node_card(raw: Any) -> dict[str, Any]:
    """Public fields only. The node pubkey is not copied out."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("getnodeinfo failed") from exc
    node = data.get("node")
    if not isinstance(node, dict):
        raise LndUnavailable("getnodeinfo failed")
    alias = _alias(node.get("alias"))
    channels = _uint(data.get("num_channels"), _MAX_CHANNELS)
    capacity = _uint(data.get("total_capacity"), _CAP)
    updated = _uint(node.get("last_update"), _MAX_TIME)
    if alias is None or channels is None or capacity is None or updated is None:
        raise LndUnavailable("getnodeinfo failed")
    addresses, truncated = _addresses(node.get("addresses"))
    out: dict[str, Any] = {
        "alias": alias,
        "num_channels": channels,
        "total_capacity_sats": capacity,
        "last_update": updated,
        "addresses": addresses,
    }
    if truncated:
        out["truncated"] = True
    return out


class _Grpc:
    """lnd-grpc-client wrapper exposing only get_node_info."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get_node_info(
        self, pub_key: str, include_channels: bool = False
    ) -> dict[str, Any]:
        """Call the stub directly. The client decorator drops NOT_FOUND."""
        try:
            from lndgrpc.common import ln
        except ImportError as exc:
            raise LndUnavailable("getnodeinfo failed") from exc
        stub = getattr(self._raw, "_ln_stub", None)
        if stub is None or not hasattr(stub, "GetNodeInfo"):
            raise LndUnavailable("getnodeinfo failed")
        try:
            raw = stub.GetNodeInfo(
                ln.NodeInfoRequest(pub_key=pub_key, include_channels=include_channels)
            )
        except (NodeNotFound, LndUnavailable):
            raise
        except Exception as exc:
            _classify(exc)
        if raw is None:
            raise LndUnavailable("getnodeinfo failed")
        return _as_dict(raw)

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Card:
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


def _get_reader(injected: _Card | None) -> _Card:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Card | None = None) -> dict[str, Any]:
    """One GetNodeInfo. Raises BadInput, BadPubkey, NodeNotFound, LndUnavailable."""
    data = _object(body)
    if set(data) != {"pubkey"}:
        raise BadInput("keys")
    pubkey = _pubkey(data.get("pubkey"))
    if pubkey is None:
        raise BadPubkey("pubkey")
    live = _get_reader(reader)
    try:
        raw = live.get_node_info(pubkey, include_channels=False)
    except (BadInput, BadPubkey, NodeNotFound, LndUnavailable):
        raise
    except Exception as exc:
        if _missing(exc):
            raise NodeNotFound("node_not_found") from exc
        raise LndUnavailable("getnodeinfo failed") from exc
    return node_card(raw)
