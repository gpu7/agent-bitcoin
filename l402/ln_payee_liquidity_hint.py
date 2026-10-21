"""Public graph capacity hint for POST /paid/lightning/ln-payee-liquidity-hint.

One GetNodeInfo with include_channels true. This is not a balance.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Protocol

_MAX_BODY = 8192
_CAP = 10**15
_MIN_AMOUNT = 100
_MAX_AMOUNT = 50_000
_MAX_EDGES = 32
_HEX = frozenset("0123456789abcdef")
_NOTE = "Public graph capacity. Not channel balances."
_lock = threading.Lock()
_reader: "_Hint | None" = None


class BadInput(Exception):
    """Missing body, bad JSON, or an unexpected key."""


class BadPubkey(Exception):
    """pubkey is not 33-byte compressed hex."""


class BadAmount(Exception):
    """amount_sats is outside 100 through 50000."""


class NodeNotFound(Exception):
    """GetNodeInfo does not know this pubkey."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, permission denied, timeout, or LND down."""


class _Hint(Protocol):
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


def _amount(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BadAmount("amount_sats must be an integer")
    if value < _MIN_AMOUNT or value > _MAX_AMOUNT:
        raise BadAmount("amount_sats out of range")
    return value


def _pubkey(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 66 or text[:2] not in ("02", "03"):
        return None
    if any(char not in _HEX for char in text):
        return None
    return text


def _missing(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "unable to find" in text or "not found" in text


def _fees(policy: Any) -> tuple[int, int] | None:
    if not isinstance(policy, dict):
        return None
    if "disabled" in policy and not isinstance(policy.get("disabled"), bool):
        return None
    if policy.get("disabled") is True:
        return None
    if "fee_base_msat" not in policy or "fee_rate_milli_msat" not in policy:
        return None
    base = _uint(policy.get("fee_base_msat"), _CAP)
    rate = _uint(policy.get("fee_rate_milli_msat"), _CAP)
    if base is None or rate is None:
        return None
    return base, rate


def _own_policy(edge: Any, pubkey: str) -> Any:
    if not isinstance(edge, dict):
        return None
    left = _pubkey(edge.get("node1_pub"))
    right = _pubkey(edge.get("node2_pub"))
    if left == pubkey:
        return edge.get("node1_policy")
    if right == pubkey:
        return edge.get("node2_policy")
    return None


def liquidity_hint(raw: Any, pubkey: str, amount_sats: int) -> dict[str, Any]:
    """Graph capacity and the payee's own public fee range. No balances."""
    try:
        data = _as_dict(raw)
    except Exception as exc:
        raise LndUnavailable("getnodeinfo failed") from exc
    capacity = _uint(data.get("total_capacity"), _CAP)
    if capacity is None:
        raise LndUnavailable("getnodeinfo failed")
    channels = data.get("channels", [])
    if channels is None:
        channels = []
    if not isinstance(channels, list):
        raise LndUnavailable("getnodeinfo failed")
    bases: list[int] = []
    rates: list[int] = []
    for edge in channels[:_MAX_EDGES]:
        parsed = _fees(_own_policy(edge, pubkey))
        if parsed is None:
            continue
        bases.append(parsed[0])
        rates.append(parsed[1])
    out: dict[str, Any] = {
        "hint": True,
        "total_capacity_sats": capacity,
        "capacity_covers_amount": capacity >= amount_sats,
        "note": _NOTE,
    }
    if bases:
        out["min_fee_base_msat"] = min(bases)
        out["max_fee_base_msat"] = max(bases)
        out["min_fee_rate_milli_msat"] = min(rates)
        out["max_fee_rate_milli_msat"] = max(rates)
    if len(channels) > _MAX_EDGES:
        out["truncated"] = True
    return out


class _Grpc:
    """lnd-grpc-client wrapper exposing only get_node_info."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def get_node_info(
        self, pub_key: str, include_channels: bool = False
    ) -> dict[str, Any]:
        return _as_dict(
            self._call("get_node_info", pub_key, include_channels=include_channels)
        )

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in _ALLOWED:
            raise LndUnavailable("method not allowed")
        return getattr(self._raw, name)(*args, **kwargs)


def connect() -> _Hint:
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


def _get_reader(injected: _Hint | None) -> _Hint:
    if injected is not None:
        return injected
    global _reader
    with _lock:
        if _reader is None:
            _reader = connect()
        return _reader


def handle_request(body: bytes, reader: _Hint | None = None) -> dict[str, Any]:
    """One GetNodeInfo. Raises BadInput, BadPubkey, BadAmount, NodeNotFound."""
    data = _object(body)
    if set(data) != {"pubkey", "amount_sats"}:
        raise BadInput("keys")
    pubkey = _pubkey(data.get("pubkey"))
    if pubkey is None:
        raise BadPubkey("pubkey")
    amount = _amount(data.get("amount_sats"))
    live = _get_reader(reader)
    try:
        raw = live.get_node_info(pubkey, include_channels=True)
    except (BadInput, BadPubkey, BadAmount, NodeNotFound, LndUnavailable):
        raise
    except Exception as exc:
        if _missing(exc):
            raise NodeNotFound("node_not_found") from exc
        raise LndUnavailable("getnodeinfo failed") from exc
    return liquidity_hint(raw, pubkey, amount)
