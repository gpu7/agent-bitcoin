"""NIP-05 check for POST /paid/nostr/nip05-verify.

One guarded HTTPS GET of /.well-known/nostr.json. No nsec and no relay.
"""

from __future__ import annotations

import errno
import hmac
import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode, urljoin, urlsplit

_MAX_BODY = 8192
_READ_LIMIT = 65_536
_TIMEOUT_S = 5.0
_LIMIT = 30
_WINDOW_S = 60.0
_NAME_MAX = 64
_DOMAIN_MAX = 253
_HEX = frozenset("0123456789abcdef")
_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._-")
_HOST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")
_REASONS = frozenset(
    {
        "pubkey_mismatch",
        "name_missing",
        "bad_json",
        "fetch_failed",
        "blocked_host",
        "not_https",
        "too_large",
        "too_many_redirects",
        "rate_limited",
    }
)
_FETCH_REASONS = frozenset(
    {
        "fetch_failed",
        "blocked_host",
        "not_https",
        "too_large",
        "too_many_redirects",
        "rate_limited",
    }
)
_REDIRECTS = {301, 302, 303, 307, 308}
_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_lock = threading.Lock()
_hits: list[float] = []


class BadInput(Exception):
    """Missing body, bad JSON, or a nip05 name that cannot be fetched."""


class BadNpub(Exception):
    """npub failed BIP-173 checks, or the value is an nsec."""


class _Blocked(Exception):
    """Host resolves to a non-public address."""


class _Failed(Exception):
    """DNS, TLS, or timeout failure. The message is not returned."""


class _TooLarge(Exception):
    """Response body exceeded the read cap."""


def _reset_limiter() -> None:
    with _lock:
        _hits.clear()


def _take(now: float) -> bool:
    with _lock:
        cutoff = now - _WINDOW_S
        while _hits and _hits[0] <= cutoff:
            del _hits[0]
        if len(_hits) >= _LIMIT:
            return False
        _hits.append(now)
        return True


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


def _npub(value: Any) -> bytes:
    if not isinstance(value, str):
        raise BadNpub("npub")
    text = value.strip()
    if text.lower().startswith("nsec"):
        raise BadNpub("nsec")
    decoded = _bech32(text)
    if decoded is None or decoded[0] != "npub" or len(decoded[1]) != 32:
        raise BadNpub("npub")
    return decoded[1]


def _domain(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    port: int | None = None
    if host.count(":") == 1:
        host, port_text = host.split(":", 1)
        if not port_text.isdigit():
            raise BadInput("domain")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise BadInput("domain")
    elif ":" in host:
        raise BadInput("domain")
    if not host or len(host) > _DOMAIN_MAX:
        raise BadInput("domain")
    if any(char not in _HOST_CHARS for char in host):
        raise BadInput("domain")
    if host[0] in ".-" or host[-1] in ".-":
        raise BadInput("domain")
    if port is None:
        return host
    return f"{host}:{port}"


def _nip05(value: Any) -> tuple[str, str]:
    if not isinstance(value, str):
        raise BadInput("nip05")
    text = value.strip()
    if text.count("@") != 1:
        raise BadInput("nip05")
    name, domain = text.split("@", 1)
    if not name or len(name) > _NAME_MAX:
        raise BadInput("nip05")
    if any(char not in _NAME_CHARS for char in name):
        raise BadInput("nip05")
    return name, _domain(domain)


def _no(reason: str) -> dict[str, Any]:
    if reason not in _REASONS:
        reason = "fetch_failed"
    return {"valid": False, "reason": reason}


def _bad_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not ip.is_global


def _dword_ip(host: str) -> ipaddress.IPv4Address | None:
    if not host.isdigit():
        return None
    number = int(host)
    if number > 0xFFFFFFFF:
        return None
    return ipaddress.IPv4Address(number)


def _reject_syntax(url: str) -> str | None:
    if not url or len(url) > 2048:
        return "bad_url"
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "bad_url"
    if parts.scheme.lower() != "https":
        return "not_https"
    if parts.username is not None or parts.password is not None:
        return "bad_url"
    if port is not None and not 1 <= port <= 65535:
        return "bad_url"
    host = parts.hostname
    if not host:
        return "bad_url"
    lowered = host.lower().rstrip(".")
    if lowered in {"localhost", "metadata.google.internal"} or lowered.endswith(
        (".localhost", ".local")
    ):
        return "blocked_host"
    dword = _dword_ip(host)
    if dword is not None:
        return "blocked_host" if _bad_ip(dword) else None
    labels = host.split(".")
    if len(labels) == 4 and all(label.isdigit() for label in labels):
        try:
            ip = ipaddress.IPv4Address(host)
        except ValueError:
            return "bad_url"
        return "blocked_host" if _bad_ip(ip) else None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None
    return "blocked_host" if _bad_ip(ip) else None


def _host_header(host: str, port: int) -> str:
    shown = f"[{host}]" if ":" in host else host
    if port == 443:
        return shown
    return f"{shown}:{port}"


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS to a resolved address, with the original name as SNI."""

    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(
            host,
            port=port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._pinned = address

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned, self.port), self.timeout)
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError as exc:
            if exc.errno != errno.ENOPROTOOPT:
                raise
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _addresses(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise _Failed() from exc
    found: list[str] = []
    for info in infos:
        raw = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError as exc:
            raise _Failed() from exc
        if _bad_ip(ip):
            raise _Blocked()
        found.append(raw)
    if not found:
        raise _Failed()
    return found


def _read_limited(response: http.client.HTTPResponse) -> bytes:
    remaining = _READ_LIMIT
    chunks: list[bytes] = []
    while remaining:
        chunk = response.read(min(8192, remaining))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        remaining -= len(chunk)
    if response.read(1):
        raise _TooLarge()
    return b"".join(chunks)


def _http_get(url: str) -> tuple[int, bytes, str | None]:
    parts = urlsplit(url)
    host = parts.hostname or ""
    port = parts.port or 443
    dword = _dword_ip(host)
    if dword is not None:
        if _bad_ip(dword):
            raise _Blocked()
        chosen = str(dword)
    else:
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None:
            if _bad_ip(literal):
                raise _Blocked()
            chosen = host
        else:
            chosen = _addresses(host, port)[0]
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    conn = _PinnedHTTPSConnection(host, chosen, port, _TIMEOUT_S)
    try:
        conn.request(
            "GET",
            path,
            headers={
                "Host": _host_header(host, port),
                "User-Agent": "agent-bitcoin-l402-inspect",
                "Accept": "application/json",
                "Connection": "close",
            },
        )
        response = conn.getresponse()
        status = int(response.status)
        location = response.headers.get("Location")
        body = _read_limited(response)
        return status, body, location
    except _TooLarge:
        raise
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise _Failed() from exc
    finally:
        conn.close()


def _with_one_redirect(
    url: str, fetch: Callable[[str], tuple[int, bytes, str | None]]
) -> tuple[int, bytes] | str:
    status, body, location = fetch(url)
    if status not in _REDIRECTS:
        return int(status), body
    if not location or not str(location).strip():
        raise _Failed()
    target = urljoin(url, str(location).strip())
    reason = _reject_syntax(target)
    if reason:
        return reason
    status2, body2, _location2 = fetch(target)
    if status2 in _REDIRECTS:
        return "too_many_redirects"
    return int(status2), body2


def _fetch_document(
    url: str,
    fetch: Callable[[str], tuple[int, bytes, str | None]] | None,
    now: float,
) -> bytes | str:
    reason = _reject_syntax(url)
    if reason:
        return reason
    if not _take(now):
        return "rate_limited"
    getter = fetch if fetch is not None else _http_get
    try:
        outcome = _with_one_redirect(url, getter)
    except _Blocked:
        return "blocked_host"
    except _Failed:
        return "fetch_failed"
    except _TooLarge:
        return "too_large"
    if isinstance(outcome, str):
        return outcome
    status, body = outcome
    if status != 200:
        return "fetch_failed"
    return body


def _judge(body: bytes, name: str, expected: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _no("bad_json")
    if not isinstance(data, dict):
        return _no("bad_json")
    names = data.get("names")
    if not isinstance(names, dict):
        return _no("bad_json")
    if name not in names:
        return _no("name_missing")
    raw = names[name]
    if not isinstance(raw, str):
        return _no("bad_json")
    hexpub = raw.strip().lower()
    if len(hexpub) != 64 or any(char not in _HEX for char in hexpub):
        return _no("pubkey_mismatch")
    try:
        got = bytes.fromhex(hexpub)
    except ValueError:
        return _no("pubkey_mismatch")
    if hmac.compare_digest(got, expected):
        return {"valid": True, "reason": ""}
    return _no("pubkey_mismatch")


def _clock(now: float | Callable[[], float] | None) -> float:
    if now is None:
        return time.time()
    if callable(now):
        return float(now())
    return float(now)


def handle_request(
    body: bytes,
    fetch: Callable[[str], tuple[int, bytes, str | None]] | None = None,
    now: float | Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Return valid and reason. Raises BadInput or BadNpub before any fetch."""
    data = _object(body)
    if set(data) != {"nip05", "npub"}:
        raise BadInput("keys")
    name, domain = _nip05(data.get("nip05"))
    expected = _npub(data.get("npub"))
    url = f"https://{domain}/.well-known/nostr.json?{urlencode({'name': name})}"
    fetched = _fetch_document(url, fetch, _clock(now))
    if isinstance(fetched, str):
        if fetched not in _FETCH_REASONS:
            fetched = "fetch_failed"
        return _no(fetched)
    return _judge(fetched, name, expected)
