"""BOLT11 policy gate for POST /paid/finance/ln-invoice-preflight.

Reuses ln_invoice_decode. No LND.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:
    from l402 import ln_invoice_decode as _decode
except ImportError:  # Docker WORKDIR /app
    import ln_invoice_decode as _decode  # type: ignore[no-redef]

SERVICE = "ln-invoice-preflight"
VERSION = "v1"
SOURCE = "local_bolt11"
FLOOR_SATS = 100
MAX_BODY_BYTES = 65_536
ALLOWED_NETWORKS = frozenset({"bitcoin", "testnet", "signet", "regtest"})


class MissingBolt11(Exception):
    """bolt11 missing or empty."""


class BadMaxSats(Exception):
    """max_sats present but not an int ≥ 100."""


class BadNetwork(Exception):
    """network present but not a known value."""


class BadInput(Exception):
    """Invalid JSON or non-object body."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(
    *,
    now: datetime,
    allow: bool,
    reasons: list[str],
    amount_sats: int | None,
    expired: bool | None = None,
    network: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": _iso_z(now),
        "ttl_s": 0,
        "source": SOURCE,
        "stale": False,
        "allow": allow,
        "reasons": reasons,
        "amount_sats": amount_sats,
    }
    if expired is not None:
        out["expired"] = expired
    if network is not None:
        out["network"] = network
    return out


def _parse_options(raw: bytes) -> tuple[str, int | None, str | None]:
    if not raw or not raw.strip():
        raise MissingBolt11("missing bolt11")
    if len(raw) > MAX_BODY_BYTES:
        raise BadInput("body too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadInput("invalid json") from exc
    if not isinstance(data, dict):
        raise BadInput("json object required")
    bolt11 = data.get("bolt11")
    if not isinstance(bolt11, str) or not bolt11.strip():
        raise MissingBolt11("missing bolt11")
    max_sats = data.get("max_sats")
    if max_sats is not None:
        if isinstance(max_sats, bool) or not isinstance(max_sats, int):
            raise BadMaxSats("max_sats must be an integer")
        if max_sats < FLOOR_SATS:
            raise BadMaxSats("max_sats below floor")
    expected = data.get("network")
    if expected is not None:
        if not isinstance(expected, str) or expected not in ALLOWED_NETWORKS:
            raise BadNetwork("invalid network")
    return bolt11.strip(), max_sats, expected


def handle_request(
    body: bytes,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or _now_utc()
    invoice, max_sats, expected_network = _parse_options(body)
    decode_body = json.dumps({"bolt11": invoice}).encode("utf-8")
    try:
        decoded = _decode.handle_request(decode_body, now=when)
    except _decode.BadInvoice:
        return _envelope(
            now=when,
            allow=False,
            reasons=["bad_invoice"],
            amount_sats=None,
        )

    amount = decoded.get("amount_sats")
    reasons: list[str] = []
    if decoded.get("expired"):
        reasons.append("expired")
    if amount is None:
        reasons.append("zero_amount")
    elif amount < FLOOR_SATS:
        reasons.append("below_floor")
    if max_sats is not None and amount is not None and amount > max_sats:
        reasons.append("above_max_sats")
    if expected_network is not None and decoded.get("network") != expected_network:
        reasons.append("network_mismatch")
    return _envelope(
        now=when,
        allow=not reasons,
        reasons=reasons,
        amount_sats=amount if isinstance(amount, int) else None,
        expired=bool(decoded.get("expired")),
        network=str(decoded.get("network") or ""),
    )
