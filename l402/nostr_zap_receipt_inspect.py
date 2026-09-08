"""NIP-57 kind-9735 inspect for POST /paid/nostr/zap-receipt-inspect.

Reuses event-verify in-process. Amount from bolt11 only. Not a zap wallet.
Never echoes content, bolt11, preimage, description-tag JSON, or sig.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

try:
    from l402 import ln_invoice_decode as _decode
    from l402 import nostr_event_verify as _verify
except ImportError:  # Docker WORKDIR /app
    import ln_invoice_decode as _decode  # type: ignore[no-redef]
    import nostr_event_verify as _verify  # type: ignore[no-redef]

SERVICE = "nostr-zap-receipt-inspect"
VERSION = "v1"
SOURCE = "local_nostr"
KIND_ZAP_RECEIPT = 9735
_HEX = frozenset("0123456789abcdef")

MissingEvent = _verify.MissingEvent


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_hex64(value: str) -> bool:
    text = value.strip().lower()
    return len(text) == 64 and all(c in _HEX for c in text)


def _first_tag(tags: Any, name: str) -> str | None:
    if not isinstance(tags, list):
        return None
    for tag in tags:
        if not isinstance(tag, list) or len(tag) < 2:
            continue
        if tag[0] != name:
            continue
        value = tag[1]
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _hex64_tag(tags: Any, name: str) -> str | None:
    raw = _first_tag(tags, name)
    if raw is None or not _is_hex64(raw):
        return None
    return raw.strip().lower()


def _amount_from_bolt11(invoice: str) -> int | None:
    """Parse sats from bolt11. Never raises; never returns the invoice string."""
    try:
        from bolt11 import decode as bolt11_decode

        parsed = bolt11_decode(invoice)
        return _decode._amount_sats(getattr(parsed, "amount_msat", None))
    except Exception:
        return None


def handle_request(
    body: bytes,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or _now_utc()
    verified = _verify.handle_request(body, now=when)
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissingEvent("missing event") from exc
    if not isinstance(data, dict):
        raise MissingEvent("missing event")

    reasons: list[str] = list(verified.get("reasons") or [])
    valid_event = bool(verified.get("valid"))
    kind = data.get("kind")
    tags = data.get("tags")

    target_pubkey = _hex64_tag(tags, "p")
    zapper_pubkey = _hex64_tag(tags, "P")
    target_event_id = _hex64_tag(tags, "e")
    bolt11 = _first_tag(tags, "bolt11")

    kind_ok = (
        isinstance(kind, int)
        and not isinstance(kind, bool)
        and kind == KIND_ZAP_RECEIPT
    )
    if not kind_ok:
        reasons.append("not_kind_9735")
    if target_pubkey is None:
        reasons.append("missing_p")
    if bolt11 is None:
        reasons.append("missing_bolt11")

    amount_sats = _amount_from_bolt11(bolt11) if bolt11 is not None else None
    if amount_sats is None:
        reasons.append("amount_unknown")

    is_zap_receipt = bool(
        valid_event and kind_ok and target_pubkey is not None and bolt11 is not None
    )

    return {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": _iso_z(when),
        "ttl_s": 0,
        "source": SOURCE,
        "stale": False,
        "valid_event": valid_event,
        "is_zap_receipt": is_zap_receipt,
        "amount_sats": amount_sats,
        "zapper_pubkey": zapper_pubkey,
        "target_pubkey": target_pubkey,
        "target_event_id": target_event_id,
        "reasons": reasons,
    }
