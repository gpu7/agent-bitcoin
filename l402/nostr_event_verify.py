"""NIP-01 id+sig check for POST /paid/nostr/event-verify.

Local coincurve Schnorr. No relays. Never echoes content/tags/sig.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

SERVICE = "nostr-event-verify"
VERSION = "v1"
SOURCE = "local_nostr"
MAX_BODY_BYTES = 65_536
_HEX = frozenset("0123456789abcdef")


class MissingEvent(Exception):
    """POST body is not a JSON object."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_hex(value: Any, length: int) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip().lower()
    return len(text) == length and all(c in _HEX for c in text)


def nip01_id(
    pubkey: str,
    created_at: int,
    kind: int,
    tags: list,
    content: str,
) -> str:
    payload = [0, pubkey, created_at, kind, tags, content]
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _schnorr_ok(pubkey_hex: str, id_hex: str, sig_hex: str) -> bool:
    try:
        from coincurve import PublicKeyXOnly

        pk = PublicKeyXOnly(bytes.fromhex(pubkey_hex))
        return bool(pk.verify(bytes.fromhex(sig_hex), bytes.fromhex(id_hex)))
    except Exception:
        return False


def handle_request(
    body: bytes,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    when = now or _now_utc()
    if not body or not body.strip():
        raise MissingEvent("missing event")
    if len(body) > MAX_BODY_BYTES:
        raise MissingEvent("missing event")
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissingEvent("missing event") from exc
    if not isinstance(data, dict):
        raise MissingEvent("missing event")

    reasons: list[str] = []
    ev_id = data.get("id")
    pubkey = data.get("pubkey")
    created_at = data.get("created_at")
    kind = data.get("kind")
    tags = data.get("tags")
    content = data.get("content")
    sig = data.get("sig")

    id_ok = _is_hex(ev_id, 64)
    pub_ok = _is_hex(pubkey, 64)
    sig_ok = _is_hex(sig, 128)
    created_ok = isinstance(created_at, int) and not isinstance(created_at, bool)
    kind_ok = isinstance(kind, int) and not isinstance(kind, bool)
    tags_ok = isinstance(tags, list)
    content_ok = isinstance(content, str)
    shape_ok = all((id_ok, pub_ok, sig_ok, created_ok, kind_ok, tags_ok, content_ok))
    if not shape_ok:
        reasons.append("bad_shape")

    id_hex = str(ev_id).strip().lower() if id_ok else None
    pub_hex = str(pubkey).strip().lower() if pub_ok else None

    if shape_ok:
        computed = nip01_id(pub_hex or "", int(created_at), int(kind), tags, content)
        if computed != id_hex:
            reasons.append("bad_id")
        if not _schnorr_ok(pub_hex or "", id_hex or "", str(sig).strip().lower()):
            reasons.append("bad_sig")

    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": _iso_z(when),
        "ttl_s": 0,
        "source": SOURCE,
        "stale": False,
        "valid": not reasons,
        "reasons": reasons,
    }
    if id_hex:
        out["id"] = id_hex
    if pub_hex:
        out["pubkey"] = pub_hex
    if kind_ok:
        out["kind"] = int(kind)
    return out
