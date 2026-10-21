"""Local profile summary for POST /paid/nostr/nostr-profile-summary.

Reads alice.pub.json and bob.pub.json only. Does not contact a relay, fetch
nip05, or accept an nsec.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

_MAX_BODY = 8192
_MAX_PUB_BYTES = 8192
_NAME_MAX = 64
_ABOUT_MAX = 128
_NIP05_MAX = 128
_PICTURE_MAX = 256
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_PRINTABLE = frozenset(chr(code) for code in range(32, 127))
_URL_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    ":/?#[]@!$&'()*+,;=-._~%"
)
_PUB_FILES = ("alice.pub.json", "bob.pub.json")
_EMPTY = {"name": "", "about": "", "nip05": "", "picture": ""}


class BadInput(Exception):
    """Missing body, bad JSON, or an unexpected key."""


class BadNpub(Exception):
    """nsec, mixed-case bech32, bad checksum, or a non-npub payload."""


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


def _polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for index in range(5):
            if (top >> index) & 1:
                chk ^= _GENERATOR[index]
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _convertbits(data: list[int], from_bits: int, to_bits: int) -> list[int] | None:
    acc = 0
    bits = 0
    out: list[int] = []
    max_value = (1 << to_bits) - 1
    for value in data:
        if value < 0 or value >> from_bits:
            return None
        acc = (acc << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            out.append((acc >> bits) & max_value)
    if bits >= from_bits or ((acc << (to_bits - bits)) & max_value):
        return None
    return out


def _bech32(text: str) -> tuple[str, bytes] | None:
    lowered = text.lower()
    if lowered != text and text.upper() != text:
        return None
    pos = lowered.rfind("1")
    if pos < 1 or pos + 7 > len(lowered):
        return None
    hrp = lowered[:pos]
    data: list[int] = []
    for char in lowered[pos + 1 :]:
        index = _CHARSET.find(char)
        if index < 0:
            return None
        data.append(index)
    if _polymod(_hrp_expand(hrp) + data) != 1:
        return None
    decoded = _convertbits(data[:-6], 5, 8)
    if decoded is None:
        return None
    return hrp, bytes(decoded)


def _require_npub(value: Any) -> str:
    if not isinstance(value, str):
        raise BadNpub("npub")
    text = value.strip()
    if text.lower().startswith("nsec"):
        raise BadNpub("nsec")
    decoded = _bech32(text)
    if decoded is None or decoded[0] != "npub" or len(decoded[1]) != 32:
        raise BadNpub("npub")
    return text.lower()


def _file_npub(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower().startswith("nsec"):
        return None
    decoded = _bech32(text)
    if decoded is None or decoded[0] != "npub" or len(decoded[1]) != 32:
        return None
    return text.lower()


def _short_npub(npub: str) -> str:
    return f"npub1…{npub[-4:]}"


def _text(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    if any(char not in _PRINTABLE for char in value):
        return ""
    return value[:limit]


def _picture(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > _PICTURE_MAX:
        return ""
    if any(char not in _URL_CHARS for char in value):
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    if parts.scheme != "https":
        return ""
    if parts.username is not None or parts.password is not None:
        return ""
    if not parts.hostname:
        return ""
    return value


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


def _pub_row(raw: bytes) -> dict[str, Any] | None:
    if len(raw) > _MAX_PUB_BYTES:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _fields(
    npub: str, directory: Path, read_bytes: Callable[[Path], bytes] | None
) -> dict[str, str]:
    if not directory.is_dir():
        return dict(_EMPTY)
    reader = read_bytes or _read_capped
    for name in _PUB_FILES:
        path = directory / name
        if not path.is_file():
            continue
        try:
            raw = reader(path)
        except OSError:
            continue
        row = _pub_row(raw)
        if row is None or _file_npub(row.get("npub")) != npub:
            continue
        return {
            "name": _text(row.get("name"), _NAME_MAX),
            "about": _text(row.get("about"), _ABOUT_MAX),
            "nip05": _text(row.get("nip05"), _NIP05_MAX),
            "picture": _picture(row.get("picture")),
        }
    return dict(_EMPTY)


def handle_request(
    body: bytes,
    *,
    directory: Path | None = None,
    read_bytes: Callable[[Path], bytes] | None = None,
) -> dict[str, Any]:
    """Return a short local profile. Raises BadInput or BadNpub before any read."""
    data = _object(body)
    if set(data) != {"npub"}:
        raise BadInput("keys")
    npub = _require_npub(data.get("npub"))
    fields = _fields(npub, directory or _default_dir(), read_bytes)
    return {"npub_short": _short_npub(npub), **fields}
