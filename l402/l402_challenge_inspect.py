"""Inspect a remote L402 402 challenge. Never pays. Never returns secrets.

GET one https URL, read WWW-Authenticate, decode the BOLT11 fields.
The macaroon and the raw invoice stay out of the response.
"""

from __future__ import annotations

import errno
import http.client
import ipaddress
import json
import re
import socket
import ssl
from typing import Any
from urllib.parse import urljoin, urlsplit

MAX_BODY_BYTES = 4096
_READ_LIMIT = 65_536
_TIMEOUT_S = 5.0
_DEFAULT_EXPIRY_S = 3600
_REDIRECTS = {301, 302, 303, 307, 308}
_CURRENCY = (
    ("bcrt", "regtest"),
    ("tbs", "signet"),
    ("bc", "mainnet"),
    ("tb", "testnet"),
)
# Same shape as agent_bitcoin.l402.client. The origin image does not import the SDK.
_CHALLENGE_RE = re.compile(
    r"""(?ix)
    (?:L402|LSAT)
    \s+
    macaroon="(?P<macaroon>[^"]+)"
    \s*,\s*
    invoice="(?P<invoice>[^"]+)"
    """
)


class MissingUrl(ValueError):
    """Body is not a JSON object or url is missing."""


class _Blocked(Exception):
    """Host resolves to a non-public address."""


class _Failed(Exception):
    """DNS, TLS, or timeout failure. The message is not returned."""


def _invalid(reason: str) -> dict[str, Any]:
    return {
        "valid_challenge": False,
        "price_sats": None,
        "expiry": None,
        "payee_pubkey": None,
        "network": None,
        "reason": reason,
    }


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


def _drain(response: http.client.HTTPResponse) -> None:
    remaining = _READ_LIMIT
    while remaining:
        chunk = response.read(min(8192, remaining))
        if not chunk:
            break
        remaining -= len(chunk)


def _http_get(url: str) -> tuple[int, str | None, str | None]:
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
                "Accept": "*/*",
                "Connection": "close",
            },
        )
        response = conn.getresponse()
        status = int(response.status)
        www_values = response.headers.get_all("WWW-Authenticate") or []
        www = ", ".join(www_values) if www_values else None
        location = response.headers.get("Location")
        _drain(response)
        return status, www, location
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise _Failed() from exc
    finally:
        conn.close()


def _with_one_redirect(url: str, fetch: Any) -> tuple[int, str | None] | str:
    status, header, location = fetch(url)
    if status not in _REDIRECTS:
        return int(status), header
    if not location or not str(location).strip():
        raise _Failed()
    target = urljoin(url, str(location).strip())
    reason = _reject_syntax(target)
    if reason:
        return reason
    status2, header2, _location2 = fetch(target)
    if status2 in _REDIRECTS:
        return "too_many_redirects"
    return int(status2), header2


def _network(currency: str) -> str | None:
    cur = currency.strip().lower()
    for prefix, name in _CURRENCY:
        if cur == prefix:
            return name
    return None


def _price_sats(amount_msat: Any) -> int | None:
    if amount_msat is None:
        return None
    msat = int(amount_msat)
    if msat <= 0:
        return None
    return msat // 1000


def _payee(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.hex()
    else:
        text = str(value).strip().lower()
    if len(text) == 66 and all(char in "0123456789abcdef" for char in text):
        return text
    return None


def _from_invoice(invoice: str, decode: Any) -> dict[str, Any]:
    if not invoice.lower().startswith("ln"):
        return _invalid("bad_invoice")
    try:
        parsed = decode(invoice)
        currency = str(getattr(parsed, "currency", "") or "")
        network = _network(currency)
        if network is None:
            return _invalid("bad_invoice")
        created = int(getattr(parsed, "date"))
        expiry_raw = getattr(parsed, "expiry", None)
        expiry_s = _DEFAULT_EXPIRY_S if expiry_raw is None else int(expiry_raw)
        if created < 0 or expiry_s < 0:
            return _invalid("bad_invoice")
        price = _price_sats(getattr(parsed, "amount_msat", None))
        payee = _payee(getattr(parsed, "payee", None))
    except Exception:
        return _invalid("bad_invoice")
    return {
        "valid_challenge": True,
        "price_sats": price,
        "expiry": created + expiry_s,
        "payee_pubkey": payee,
        "network": network,
        "reason": "",
    }


def _from_header(header: str, decode: Any) -> dict[str, Any]:
    match = _CHALLENGE_RE.search(header)
    if match is None:
        return _invalid("bad_challenge")
    do_decode = decode
    if do_decode is None:
        from bolt11 import decode as bolt11_decode

        do_decode = bolt11_decode
    return _from_invoice(match.group("invoice"), do_decode)


def inspect(url: str, *, fetch: Any = None, decode: Any = None) -> dict[str, Any]:
    text = url.strip()
    reason = _reject_syntax(text)
    if reason:
        return _invalid(reason)
    getter = fetch if fetch is not None else _http_get
    try:
        outcome = _with_one_redirect(text, getter)
    except _Blocked:
        return _invalid("blocked_host")
    except _Failed:
        return _invalid("fetch_failed")
    if isinstance(outcome, str):
        return _invalid(outcome)
    status, header = outcome
    if status != 402:
        return _invalid("not_402")
    if header is None or not str(header).strip():
        return _invalid("missing_challenge")
    return _from_header(str(header), decode)


def handle_request(
    body: bytes, *, fetch: Any = None, decode: Any = None
) -> dict[str, Any]:
    if len(body) > MAX_BODY_BYTES:
        raise MissingUrl("too_large")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissingUrl("bad_json") from exc
    if not isinstance(payload, dict) or "url" not in payload:
        raise MissingUrl("missing_url")
    url = payload["url"]
    if not isinstance(url, str):
        raise MissingUrl("missing_url")
    return inspect(url, fetch=fetch, decode=decode)
