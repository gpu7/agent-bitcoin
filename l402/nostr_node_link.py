"""Public npub link for POST /paid/nostr/nostr-node-link.

Reads alice.pub.json and bob.pub.json only. Never opens an nsec or *.enc.json.
GetInfo runs only after a public npub file matches. A down node is not linked.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

_MAX_BODY = 8192
_MAX_PUB_BYTES = 8192
_NPUB_LEN = 63
_BECH32 = frozenset("qpzry9x8gf2tvdw0s3jn54khce6mua7l")
_HEX = frozenset("0123456789abcdef")
_PUB_FILES = ("alice.pub.json", "bob.pub.json")
_lock = threading.Lock()
_reader: "_Info | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or a non-object."""


class BadNpub(Exception):
    """nsec, a non-npub, or a bad bech32 character."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Info(Protocol):
    """Narrow LND surface. GetInfo only."""

    def get_info(self) -> dict[str, Any]: ...


_ALLOWED = frozenset({"get_info"})


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


def _short_npub(npub: str) -> str:
    return f"npub1…{npub[-4:]}"


def _parse_npub(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != _NPUB_LEN or not text.startswith("npub1"):
        return None
    if any(char not in _BECH32 for char in text[5:]):
        return None
    return text


def _require_npub(value: Any) -> str:
    if not isinstance(value, str):
        raise BadNpub("bad npub")
    text = value.strip().lower()
    if text.startswith("nsec"):
        raise BadNpub("nsec rejected")
    parsed = _parse_npub(text)
    if parsed is None:
        raise BadNpub("bad npub")
    return parsed


def _default_dir() -> Path:
    override = (os.environ.get("NOSTR_POC_DIR") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / ".nostr-poc-mainnet"


def _read_capped(path: Path) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(_MAX_PUB_BYTES + 1)
    if len(raw) > _MAX_PUB_BYTES:
        raise OSError("pub file too large")
    return raw


def _npub_in_file(raw: bytes) -> str | None:
    if len(raw) > _MAX_PUB_BYTES:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return _parse_npub(data.get("npub"))


def _load_pubs(
    directory: Path, read_bytes: Callable[[Path], bytes] | None
) -> list[str]:
    if not directory.is_dir():
        return []
    reader = read_bytes or _read_capped
    found: list[str] = []
    for name in _PUB_FILES:
        path = directory / name
        if not path.is_file():
            continue
        try:
            raw = reader(path)
        except OSError:
            continue
        npub = _npub_in_file(raw)
        if npub:
            found.append(npub)
    return found


def _identity(reader: _Info | None) -> str | None:
    live = reader
    if live is None:
        try:
            live = _get_reader(None)
        except LndUnavailable:
            return None
    try:
        data = _as_dict(live.get_info())
    except Exception:
        return None
    return _pubkey(data.get("identity_pubkey"))


def _linked_row(npub: str, identity: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {"npub": _short_npub(npub), "link": "not linked"}
    if identity:
        row["link"] = "linked"
        row["identity_pubkey"] = _short_pubkey(identity)
    return row


class _Grpc:
    """lnd-grpc-client wrapper exposing only get_info."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get_info(self) -> dict[str, Any]:
        return _as_dict(self._call("get_info"))

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


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
    return _Grpc(raw)


def _get_reader(injected: _Info | None) -> _Info:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(
    body: bytes,
    reader: _Info | None = None,
    *,
    directory: Path | None = None,
    read_bytes: Callable[[Path], bytes] | None = None,
) -> dict[str, Any]:
    """Return a short npub and whether it matches a public file plus this node."""
    data = _object(body)
    requested: str | None = None
    if "npub" in data:
        requested = _require_npub(data.get("npub"))
    pubs = _load_pubs(directory or _default_dir(), read_bytes)
    if requested is not None:
        identity = _identity(reader) if requested in pubs else None
        return _linked_row(requested, identity)
    if not pubs:
        return {"nodes": [], "link": "not linked"}
    identity = _identity(reader)
    rows = [_linked_row(npub, identity) for npub in pubs[:2]]
    link = "linked" if any(row["link"] == "linked" for row in rows) else "not linked"
    return {"nodes": rows, "link": link}
