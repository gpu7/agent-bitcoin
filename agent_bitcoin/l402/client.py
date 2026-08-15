"""Pay an Aperture L402 challenge and retry the HTTP request."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from agent_bitcoin.client import AgentBitcoinClient, _invoice_amount_sats
from agent_bitcoin.constants import DEFAULT_L402_PRICE_SATS, min_payment_sats
from agent_bitcoin.exceptions import PaymentError


# Aperture / LSAT WWW-Authenticate: L402 macaroon="...", invoice="ln..."
_CHALLENGE_RE = re.compile(
    r"""(?ix)
    (?:L402|LSAT)
    \s+
    macaroon="(?P<macaroon>[^"]+)"
    \s*,\s*
    invoice="(?P<invoice>[^"]+)"
    """
)


class _Payer(Protocol):
    min_payment_sats: int

    def pay_invoice(self, payment_request: str, fee_limit_sats: int = 200) -> Any: ...


@dataclass(frozen=True)
class L402Challenge:
    macaroon: str
    invoice: str


@dataclass
class L402Response:
    status_code: int
    headers: dict[str, str]
    body: bytes
    paid: bool
    challenge: L402Challenge | None = None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text())


def parse_www_authenticate(header: str | None) -> L402Challenge:
    """Parse an Aperture/LSAT WWW-Authenticate header."""
    if not header or not str(header).strip():
        raise ValueError("WWW-Authenticate header is missing")
    match = _CHALLENGE_RE.search(header)
    if not match:
        raise ValueError(f"unrecognized L402 WWW-Authenticate header: {header!r}")
    return L402Challenge(
        macaroon=match.group("macaroon"),
        invoice=match.group("invoice"),
    )


def authorization_value(macaroon: str, preimage_hex: str) -> str:
    preimage = preimage_hex.strip().lower().removeprefix("0x")
    if not re.fullmatch(r"[0-9a-f]+", preimage) or len(preimage) < 64:
        raise ValueError("preimage must be at least 32 bytes of hex")
    return f"L402 {macaroon}:{preimage}"


def _header_map(headers: Any) -> dict[str, str]:
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    if callable(items):
        return {str(k): str(v) for k, v in items()}
    return {str(k): str(v) for k, v in dict(headers).items()}


def _read_http_error(exc: HTTPError) -> tuple[int, dict[str, str], bytes]:
    try:
        body = exc.read() or b""
    except Exception:
        body = b""
    return int(exc.code), _header_map(exc.headers), body


class L402Client:
    """HTTP client that pays one L402 invoice via AgentBitcoinClient."""

    def __init__(
        self,
        payer: AgentBitcoinClient | _Payer,
        *,
        expected_price_sats: int | None = None,
        fee_limit_sats: int = 200,
        timeout_seconds: float = 30,
    ) -> None:
        self.payer = payer
        self.expected_price_sats = (
            DEFAULT_L402_PRICE_SATS
            if expected_price_sats is None
            else int(expected_price_sats)
        )
        self.fee_limit_sats = int(fee_limit_sats)
        self.timeout_seconds = float(timeout_seconds)

    def fetch(self, url: str) -> L402Response:
        status, headers, body = self._get(url, auth=None)
        if status != 402:
            return L402Response(
                status_code=status, headers=headers, body=body, paid=False
            )

        challenge = parse_www_authenticate(
            headers.get("WWW-Authenticate") or headers.get("www-authenticate")
        )
        self._assert_invoice_price(challenge.invoice)
        result = self.payer.pay_invoice(
            challenge.invoice, fee_limit_sats=self.fee_limit_sats
        )
        if not getattr(result, "success", False):
            raise PaymentError(
                f"L402 invoice payment failed: {getattr(result, 'status', 'UNKNOWN')}"
            )
        preimage = getattr(result, "preimage", None)
        if not preimage:
            raise PaymentError(
                "L402 payment succeeded but LND did not return a payment preimage"
            )

        auth = authorization_value(challenge.macaroon, str(preimage))
        status2, headers2, body2 = self._get(url, auth=auth)
        return L402Response(
            status_code=status2,
            headers=headers2,
            body=body2,
            paid=True,
            challenge=challenge,
        )

    def _assert_invoice_price(self, invoice: str) -> None:
        amount = 0
        decode = getattr(self.payer, "lnd", None)
        if decode is not None and hasattr(decode, "decode_pay_req"):
            decoded = decode.decode_pay_req(invoice)
            amount = _invoice_amount_sats(decoded)
        if amount <= 0:
            raise ValueError("L402 invoice has no readable sat amount")
        floor = getattr(self.payer, "min_payment_sats", None) or min_payment_sats()
        if amount < int(floor):
            raise ValueError(f"L402 invoice {amount} sats is below minimum {floor}")
        if amount != self.expected_price_sats:
            raise ValueError(
                f"L402 invoice {amount} sats != expected price "
                f"{self.expected_price_sats}"
            )

    def _get(self, url: str, auth: str | None) -> tuple[int, dict[str, str], bytes]:
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = auth
        req = Request(url, method="GET", headers=headers)
        try:
            with urlopen(req, timeout=self.timeout_seconds) as resp:
                return int(resp.status), _header_map(resp.headers), resp.read() or b""
        except HTTPError as exc:
            return _read_http_error(exc)
