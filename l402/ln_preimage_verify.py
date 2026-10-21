"""SHA-256 preimage check for POST /paid/lightning/ln-preimage-verify.

No LND. The preimage and payment hash stay out of the response.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

_MAX_BODY = 8192
_HEX = frozenset("0123456789abcdef")


class BadInput(Exception):
    """Missing body, bad JSON, or a value that is not 32 bytes of hex."""


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


def _hex32(value: Any) -> bytes:
    if not isinstance(value, str):
        raise BadInput("hex required")
    text = value.strip().lower()
    if len(text) != 64 or any(char not in _HEX for char in text):
        raise BadInput("hex required")
    return bytes.fromhex(text)


def handle_request(body: bytes) -> dict[str, bool]:
    """Return only valid. Raises BadInput before hashing on a bad body."""
    data = _object(body)
    if set(data) != {"payment_hash", "preimage"}:
        raise BadInput("keys")
    payment_hash = _hex32(data["payment_hash"])
    preimage = _hex32(data["preimage"])
    digest = hashlib.sha256(preimage).digest()
    return {"valid": hmac.compare_digest(digest, payment_hash)}
