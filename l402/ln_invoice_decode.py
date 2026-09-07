"""In-process BOLT11 inspect for POST /paid/finance/ln-invoice-decode.

No LND. No QueryRoutes / SendPayment / DecodePayReq.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

SERVICE = "ln-invoice-decode"
VERSION = "v1"
SOURCE = "local_bolt11"
MAX_BODY_BYTES = 65_536
MAX_DESCRIPTION_CHARS = 200
DEFAULT_EXPIRY_S = 3600

# Longest currency first so bcrt is not classified as bc.
_CURRENCY_NETWORK = (
    ("bcrt", "regtest"),
    ("tbs", "signet"),
    ("bc", "bitcoin"),
    ("tb", "testnet"),
)


class BadInvoice(Exception):
    """Missing, empty, or unparseable bolt11."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate_prefix(value: str) -> str:
    text = value.strip()
    if len(text) <= 12:
        return text
    return text[:8] + "…"


def _network(currency: str) -> str:
    cur = (currency or "").strip().lower()
    for prefix, network in _CURRENCY_NETWORK:
        if cur == prefix:
            return network
    raise BadInvoice("unknown invoice network")


def _amount_sats(amount_msat: Any) -> int | None:
    if amount_msat is None:
        return None
    try:
        msat = int(amount_msat)
    except (TypeError, ValueError) as exc:
        raise BadInvoice("invalid amount") from exc
    if msat <= 0:
        return None
    return int(math.floor(msat / 1000))


def parse_body(raw: bytes) -> str:
    if not raw or not raw.strip():
        raise BadInvoice("empty body")
    if len(raw) > MAX_BODY_BYTES:
        raise BadInvoice("body too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BadInvoice("invalid json") from exc
    if not isinstance(data, dict):
        raise BadInvoice("json object required")
    bolt11 = data.get("bolt11")
    if not isinstance(bolt11, str) or not bolt11.strip():
        raise BadInvoice("bolt11 required")
    invoice = bolt11.strip()
    if not invoice.lower().startswith("ln"):
        raise BadInvoice("bolt11 must be a Lightning invoice")
    return invoice


def digest_invoice(
    invoice: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or _now_utc()
    currency = str(getattr(invoice, "currency", "") or "")
    network = _network(currency)
    dest = str(getattr(invoice, "payee", "") or "").strip().lower()
    payment_hash = str(getattr(invoice, "payment_hash", "") or "").strip().lower()
    if len(dest) != 66 or any(c not in "0123456789abcdef" for c in dest):
        raise BadInvoice("dest_pubkey missing")
    if len(payment_hash) != 64 or any(
        c not in "0123456789abcdef" for c in payment_hash
    ):
        raise BadInvoice("payment_hash missing")
    date = getattr(invoice, "date", None)
    try:
        created = int(date)
    except (TypeError, ValueError) as exc:
        raise BadInvoice("timestamp missing") from exc
    expiry_s = getattr(invoice, "expiry", None)
    try:
        expiry_s_int = int(expiry_s) if expiry_s is not None else DEFAULT_EXPIRY_S
    except (TypeError, ValueError):
        expiry_s_int = DEFAULT_EXPIRY_S
    if expiry_s_int < 0:
        expiry_s_int = DEFAULT_EXPIRY_S
    expiry_unix = created + expiry_s_int
    now_unix = int(when.timestamp())
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": _iso_z(when),
        "ttl_s": 0,
        "source": SOURCE,
        "stale": False,
        "network": network,
        "amount_sats": _amount_sats(getattr(invoice, "amount_msat", None)),
        "dest_pubkey": dest,
        "payment_hash": payment_hash,
        "expiry_unix": expiry_unix,
        "expired": now_unix >= expiry_unix,
    }
    description = getattr(invoice, "description", None)
    if (
        isinstance(description, str)
        and description
        and len(description) <= MAX_DESCRIPTION_CHARS
    ):
        out["description"] = description
    return out


def handle_request(
    body: bytes,
    *,
    now: datetime | None = None,
    decode=None,
) -> dict[str, Any]:
    """Parse POST body. Raises BadInvoice. Never logs full bolt11."""
    invoice_s = parse_body(body)
    do_decode = decode
    if do_decode is None:
        from bolt11 import decode as bolt11_decode

        do_decode = bolt11_decode
    try:
        parsed = do_decode(invoice_s)
    except BadInvoice:
        raise
    except Exception as exc:
        raise BadInvoice(_truncate_prefix(invoice_s)) from exc
    return digest_invoice(parsed, now=now)
