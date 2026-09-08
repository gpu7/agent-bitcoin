"""NIP-19 bech32 → type+hex for POST /paid/nostr/npub-decode.

Never converts nsec to hex. No relays. Do not echo entity.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

SERVICE = "nostr-npub-decode"
VERSION = "v1"
SOURCE = "local_nostr"
MAX_BODY_BYTES = 65_536
MAX_RELAYS = 8
_SIMPLE = {"npub": "npub", "note": "note"}
_TLV = {"nprofile": "nprofile", "nevent": "nevent"}
_HEX = frozenset("0123456789abcdef")


class MissingEntity(Exception):
    """entity missing or body is not a JSON object."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _envelope(
    *,
    now: datetime,
    valid: bool,
    reasons: list[str],
    type_name: str | None = None,
    hex_val: str | None = None,
    relays: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": _iso_z(now),
        "ttl_s": 0,
        "source": SOURCE,
        "stale": False,
        "valid": valid,
        "reasons": reasons,
    }
    if valid and type_name:
        out["type"] = type_name
    if valid and hex_val:
        out["hex"] = hex_val
    if valid and relays:
        out["relays"] = relays
    return out


def _relay_ok(url: str) -> bool:
    text = url.strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme in ("ws", "wss") and bool(parsed.netloc)


def _parse_tlv(payload: bytes) -> tuple[bytes | None, list[str]]:
    special: bytes | None = None
    relays: list[str] = []
    i = 0
    n = len(payload)
    while i + 2 <= n:
        typ = payload[i]
        length = payload[i + 1]
        i += 2
        if i + length > n:
            break
        value = payload[i : i + length]
        i += length
        if typ == 0 and special is None and length == 32:
            special = bytes(value)
        elif typ == 1 and len(relays) < MAX_RELAYS:
            try:
                url = value.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if _relay_ok(url):
                relays.append(url.strip())
    return special, relays


def handle_request(
    body: bytes,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or _now_utc()
    if not body or not body.strip() or len(body) > MAX_BODY_BYTES:
        raise MissingEntity("missing entity")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissingEntity("missing entity") from exc
    if not isinstance(data, dict):
        raise MissingEntity("missing entity")
    entity = data.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        raise MissingEntity("missing entity")
    entity = entity.strip()

    from bech32 import bech32_decode, convertbits

    decoded = bech32_decode(entity)
    if not decoded or decoded[0] is None or decoded[1] is None:
        return _envelope(now=when, valid=False, reasons=["bad_bech32"])
    hrp, words = decoded
    hrp = (hrp or "").lower()

    if hrp == "nsec":
        return _envelope(now=when, valid=False, reasons=["nsec_rejected"])

    payload = convertbits(words, 5, 8, False)
    if payload is None:
        return _envelope(now=when, valid=False, reasons=["bad_bech32"])
    raw = bytes(payload)

    if hrp in _SIMPLE:
        if len(raw) != 32:
            return _envelope(now=when, valid=False, reasons=["bad_bech32"])
        hex_val = raw.hex()
        if len(hex_val) != 64 or any(c not in _HEX for c in hex_val):
            return _envelope(now=when, valid=False, reasons=["bad_bech32"])
        return _envelope(
            now=when, valid=True, reasons=[], type_name=hrp, hex_val=hex_val
        )

    if hrp in _TLV:
        special, relays = _parse_tlv(raw)
        if special is None or len(special) != 32:
            return _envelope(now=when, valid=False, reasons=["bad_bech32"])
        hex_val = special.hex()
        return _envelope(
            now=when,
            valid=True,
            reasons=[],
            type_name=hrp,
            hex_val=hex_val,
            relays=relays or None,
        )

    return _envelope(now=when, valid=False, reasons=["unsupported_hrp"])
