"""Lightning path-fee hint for POST /paid/finance/ln-path-fee-hint.

Readonly QueryRoutes + DecodePayReq only. Not Terminal/RTL. Does not pay.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

DEFAULT_TTL_S = 15
MIN_TTL_S = 10
MAX_TTL_S = 30
FETCH_TIMEOUT_S = 3.0
SERVICE = "ln-path-fee-hint"
VERSION = "v1"
SOURCE = "aws_agent_lnd"
MIN_AMOUNT_SATS = 100
MAX_AMOUNT_SATS = 50_000
MAX_BODY_BYTES = 65_536
_PUBKEY_RE = re.compile(r"^(?:02|03)[0-9a-fA-F]{64}$")


class BadInput(Exception):
    """XOR / amount / pubkey / invoice parse failed."""


class NoRoute(Exception):
    """LND QueryRoutes found no path."""


class LndUnavailable(Exception):
    """Cert/macaroon missing, timeout, or LND down."""


class LndHintRouter(Protocol):
    """Narrow LND surface. Must not include spend RPCs."""

    def decode_pay_req(self, bolt11: str) -> dict[str, Any]: ...

    def query_routes(self, dest: str, amount_sats: int) -> dict[str, Any]: ...


_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any] | NoRoute]] = {}
_router: LndHintRouter | None = None


def reset_cache() -> None:
    global _cache, _router
    with _lock:
        _cache = {}
        _router = None


def ttl_s_from_env() -> int:
    raw = os.environ.get("LN_PATH_HINT_TTL_S", "").strip()
    if not raw:
        return DEFAULT_TTL_S
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_S
    return max(MIN_TTL_S, min(MAX_TTL_S, value))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate_bolt11(value: str) -> str:
    text = value.strip()
    if len(text) <= 20:
        return text
    return text[:12] + "…"


def parse_body(raw: bytes) -> dict[str, Any]:
    """Validate XOR input. Does not echo bolt11."""
    if not raw or not raw.strip():
        raise BadInput("empty body")
    if len(raw) > MAX_BODY_BYTES:
        raise BadInput("body too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadInput("invalid json") from exc
    if not isinstance(data, dict):
        raise BadInput("json object required")

    bolt11 = data.get("bolt11")
    dest = data.get("dest_pubkey")
    amount_raw = data.get("amount_sats")
    has_bolt11 = isinstance(bolt11, str) and bool(bolt11.strip())
    has_dest = isinstance(dest, str) and bool(dest.strip())
    if has_bolt11 and has_dest:
        raise BadInput("bolt11 and dest_pubkey are mutually exclusive")
    if not has_bolt11 and not has_dest:
        raise BadInput("bolt11 or dest_pubkey required")

    amount: int | None = None
    if amount_raw is not None:
        if isinstance(amount_raw, bool) or not isinstance(amount_raw, int):
            raise BadInput("amount_sats must be an integer")
        amount = amount_raw
        if amount < MIN_AMOUNT_SATS or amount > MAX_AMOUNT_SATS:
            raise BadInput("amount_sats out of range")

    if has_dest:
        pubkey = str(dest).strip().lower()
        if not _PUBKEY_RE.fullmatch(pubkey):
            raise BadInput("dest_pubkey must be 33-byte compressed hex")
        if amount is None:
            raise BadInput("amount_sats required with dest_pubkey")
        return {"kind": "dest", "dest": pubkey, "amount_sats": amount}

    invoice = str(bolt11).strip()
    if not invoice.lower().startswith("ln"):
        raise BadInput("bolt11 must be a Lightning invoice")
    return {
        "kind": "bolt11",
        "bolt11": invoice,
        "amount_sats": amount,
        "bolt11_log": _truncate_bolt11(invoice),
    }


def _as_dict(msg: Any) -> dict[str, Any]:
    if isinstance(msg, dict):
        return msg
    from google.protobuf.json_format import MessageToDict

    return MessageToDict(msg, preserving_proto_field_name=True)


def _intish(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _invoice_amount_sats(decoded: dict[str, Any]) -> int:
    sats = decoded.get("num_satoshis")
    if sats not in (None, "", "0"):
        return _intish(sats)
    msat = decoded.get("num_msat")
    if msat not in (None, "", "0"):
        return _intish(msat) // 1000
    return 0


def digest_route(
    route_resp: dict[str, Any],
    *,
    amount_sats: int,
    now: datetime | None = None,
    ttl_s: int | None = None,
    stale: bool = False,
) -> dict[str, Any]:
    routes = route_resp.get("routes") or []
    if not routes:
        raise NoRoute("no_route")
    first = routes[0]
    hops = first.get("hops") or []
    if "total_fees_msat" in first:
        fee_sats = int(math.ceil(_intish(first.get("total_fees_msat")) / 1000.0))
    else:
        fee_sats = _intish(first.get("total_fees"))
    hop_count = len(hops)
    if hop_count < 1:
        raise NoRoute("no_route")
    ttl = DEFAULT_TTL_S if ttl_s is None else int(ttl_s)
    ttl = max(MIN_TTL_S, min(MAX_TTL_S, ttl))
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": _iso_z(now or _now_utc()),
        "ttl_s": ttl,
        "source": SOURCE,
        "stale": bool(stale),
        "amount_sats": int(amount_sats),
        "fee_sats": fee_sats,
        "total_sats": int(amount_sats) + fee_sats,
        "hop_count": hop_count,
    }
    if "success_prob" in route_resp:
        try:
            out["success_hint"] = float(route_resp["success_prob"])
        except (TypeError, ValueError):
            pass
    return out


def _cache_key(parsed: dict[str, Any], decoded: dict[str, Any] | None) -> str:
    if decoded and decoded.get("payment_hash"):
        return "h:" + str(decoded["payment_hash"])
    dest = parsed.get("dest") or (decoded or {}).get("dest") or ""
    amount = parsed.get("amount_sats") or (decoded or {}).get("amount_sats") or 0
    return f"d:{dest}:{amount}"


def _resolve_invoice(
    parsed: dict[str, Any], router: LndHintRouter
) -> tuple[str, int, dict[str, Any]]:
    """Return dest, amount_sats, decoded dict. Never logs full bolt11."""
    if parsed["kind"] == "dest":
        return parsed["dest"], parsed["amount_sats"], {}
    try:
        decoded = _as_dict(router.decode_pay_req(parsed["bolt11"]))
    except (BadInput, NoRoute, LndUnavailable):
        raise
    except Exception as exc:
        text = str(exc).lower()
        if any(
            token in text
            for token in (
                "invalid",
                "checksum",
                "bech32",
                "decode",
                "payreq",
                "payment request",
            )
        ):
            raise BadInput("invoice parse failed") from exc
        raise LndUnavailable("decode failed") from exc
    dest = str(decoded.get("destination") or decoded.get("dest") or "").strip().lower()
    if not _PUBKEY_RE.fullmatch(dest):
        raise BadInput("invoice dest missing")
    inv_amt = _invoice_amount_sats(decoded)
    provided = parsed.get("amount_sats")
    if inv_amt <= 0:
        if provided is None:
            raise BadInput("zero-amount invoice requires amount_sats")
        amount = provided
    else:
        if provided is not None and provided != inv_amt:
            raise BadInput("amount_sats does not match invoice")
        amount = inv_amt
        if amount < MIN_AMOUNT_SATS or amount > MAX_AMOUNT_SATS:
            raise BadInput("invoice amount out of range")
    return dest, amount, decoded


def _is_no_route(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(
        token in text
        for token in (
            "no_route",
            "no route",
            "unable to find a path",
            "unable to find a route",
            "destination unroutable",
        )
    )


class _GrpcHintRouter:
    """lnd-grpc-client wrapper exposing only decode + query_routes."""

    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def decode_pay_req(self, bolt11: str) -> dict[str, Any]:
        return _as_dict(self._raw.decode_pay_req(bolt11))

    def query_routes(self, dest: str, amount_sats: int) -> dict[str, Any]:
        return _as_dict(self._raw.query_routes(dest, amount_sats))


def connect_router() -> LndHintRouter:
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
    return _GrpcHintRouter(raw)


def _get_router(injected: LndHintRouter | None) -> LndHintRouter:
    if injected is not None:
        return injected
    global _router
    with _lock:
        if _router is None:
            _router = connect_router()
        return _router


def _query(router: LndHintRouter, dest: str, amount_sats: int) -> dict[str, Any]:
    try:
        return router.query_routes(dest, amount_sats)
    except NoRoute:
        raise
    except LndUnavailable:
        raise
    except Exception as exc:
        if _is_no_route(exc):
            raise NoRoute("no_route") from exc
        raise LndUnavailable("queryroutes failed") from exc


def handle_request(
    body: bytes,
    *,
    router: LndHintRouter | None = None,
    now: datetime | None = None,
    ttl_s: int | None = None,
    monotonic: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Parse POST body and return a 200 digest. Raises BadInput/NoRoute/LndUnavailable."""
    parsed = parse_body(body)
    ttl = (
        ttl_s_from_env()
        if ttl_s is None
        else max(MIN_TTL_S, min(MAX_TTL_S, int(ttl_s)))
    )
    clock = monotonic or time.monotonic
    when = now or _now_utc()
    live = _get_router(router)

    try:
        dest, amount, decoded = _resolve_invoice(parsed, live)
    except BadInput:
        raise
    except Exception as exc:
        if isinstance(exc, (NoRoute, LndUnavailable)):
            raise
        raise LndUnavailable("decode failed") from exc

    key = _cache_key({**parsed, "dest": dest, "amount_sats": amount}, decoded)
    with _lock:
        hit = _cache.get(key)
        if hit is not None and (clock() - hit[0]) < ttl:
            cached = hit[1]
            if isinstance(cached, NoRoute):
                raise NoRoute("no_route")
            return dict(cached)
        try:
            raw = _query(live, dest, amount)
            payload = digest_route(raw, amount_sats=amount, now=when, ttl_s=ttl)
            _cache[key] = (clock(), payload)
            return dict(payload)
        except NoRoute as exc:
            _cache[key] = (clock(), NoRoute("no_route"))
            raise NoRoute("no_route") from exc
        except LndUnavailable:
            if hit is not None and not isinstance(hit[1], NoRoute):
                stale = dict(hit[1])
                stale["stale"] = True
                return stale
            raise
