"""Lightning address metadata for POST /paid/lightning/ln-address-resolve.

One guarded HTTPS GET of LNURL pay metadata. Does not request an invoice.
"""

from __future__ import annotations

import errno
import http.client
import ipaddress
import json
import socket
import ssl
import threading
import time
from typing import Any, Callable
from urllib.parse import quote, urljoin, urlsplit

_MAX_BODY = 8192
_READ_LIMIT = 65_536
_TIMEOUT_S = 5.0
_LIMIT = 30
_WINDOW_S = 60.0
_USER_MAX = 64
_DOMAIN_MAX = 253
_TEXT_MAX = 128
_META_MAX = 8192
_CAP = 10**15
_HOST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")
_REASONS = frozenset(
    {
        "blocked_host",
        "not_https",
        "too_large",
        "too_many_redirects",
        "rate_limited",
        "fetch_failed",
        "bad_json",
        "bad_pay_request",
    }
)
_REDIRECTS = {301, 302, 303, 307, 308}
_lock = threading.Lock()
_hits: list[float] = []


class BadInput(Exception):
    """Missing body, bad JSON, or an address that cannot be fetched."""


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


def _reason(reason: str) -> dict[str, str]:
    if reason not in _REASONS:
        reason = "fetch_failed"
    return {"reason": reason}


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


def _user_ok(user: str) -> bool:
    if not user or len(user) > _USER_MAX or user in {".", ".."} or ".." in user:
        return False
    for char in user:
        code = ord(char)
        if code < 33 or code > 126 or char in "/?@":
            return False
    return True


def _address(value: Any) -> tuple[str, str]:
    if not isinstance(value, str):
        raise BadInput("address")
    text = value.strip()
    if text.count("@") != 1:
        raise BadInput("address")
    user, domain = text.split("@", 1)
    if not _user_ok(user):
        raise BadInput("address")
    return user, _domain(domain)


def _msat(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0 or value > _CAP:
        return None
    return value


def _printable(value: str) -> bool:
    return all(32 <= ord(char) <= 126 for char in value)


def _description(data: dict[str, Any]) -> str | None:
    meta = data.get("metadata")
    if not isinstance(meta, str) or len(meta) > _META_MAX:
        return None
    try:
        pairs = json.loads(meta)
    except json.JSONDecodeError:
        return None
    if not isinstance(pairs, list):
        return None
    for item in pairs:
        if not isinstance(item, list) or len(item) < 2:
            continue
        if item[0] != "text/plain" or not isinstance(item[1], str):
            continue
        text = item[1].strip()
        if not text or not _printable(text):
            return None
        return text[:_TEXT_MAX]
    return None


def _bad_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not ip.is_global


def _callback_domain(data: dict[str, Any]) -> str | None:
    callback = data.get("callback")
    if not isinstance(callback, str) or not callback.strip() or len(callback) > 2048:
        return None
    text = callback.strip()
    if _reject_syntax(text):
        return None
    host = urlsplit(text).hostname
    if not host:
        return None
    host = host.lower().rstrip(".")
    if not host or not _printable(host) or any(char.isspace() for char in host):
        return None
    return host[:_DOMAIN_MAX]


def _pay_request(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _reason("bad_json")
    if not isinstance(data, dict):
        return _reason("bad_json")
    if data.get("tag") != "payRequest":
        return _reason("bad_pay_request")
    minimum = _msat(data.get("minSendable"))
    maximum = _msat(data.get("maxSendable"))
    if minimum is None or maximum is None:
        return _reason("bad_json")
    out: dict[str, Any] = {
        "min_sats": minimum // 1000,
        "max_sats": maximum // 1000,
    }
    description = _description(data)
    if description is not None:
        out["description"] = description
    domain = _callback_domain(data)
    if domain is not None:
        out["callback_domain"] = domain
    return out


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
    """Return the pay range. Raises BadInput before any fetch."""
    data = _object(body)
    if set(data) != {"address"}:
        raise BadInput("keys")
    user, domain = _address(data.get("address"))
    url = f"https://{domain}/.well-known/lnurlp/{quote(user, safe='')}"
    fetched = _fetch_document(url, fetch, _clock(now))
    if isinstance(fetched, str):
        return _reason(fetched)
    return _pay_request(fetched)
