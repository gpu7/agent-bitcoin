"""Remote L402 challenge inspect. No LND and no payment."""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from l402 import l402_challenge_inspect as inspect
from l402.origin import dispatch

_ROUTE = "/paid/security/l402-challenge-inspect"
_URL = "https://merchant.example/paid"
_MACAROON = "macaroon-secret-value-not-returned"
_INVOICE = "lnbc100n1secretinvoice-not-returned"
_PAYEE = "02" + "ab" * 32


def _body(url: str) -> bytes:
    return json.dumps({"url": url}).encode()


def _challenge(macaroon: str = _MACAROON, invoice: str = _INVOICE) -> str:
    return f'L402 macaroon="{macaroon}", invoice="{invoice}"'


class _Parsed:
    def __init__(
        self, *, amount_msat: int | None = 100_000, currency: str = "bc"
    ) -> None:
        self.currency = currency
        self.amount_msat = amount_msat
        self.date = 2_000_000_000
        self.expiry = 600
        self.payee = _PAYEE


def _decode(invoice: str) -> _Parsed:
    if invoice != _INVOICE:
        raise AssertionError(invoice)
    return _Parsed()


def _fetch_402(header: str | None):
    def fetch(url: str):
        assert url == _URL
        return 402, header, None

    return fetch


def test_known_good_mock_402() -> None:
    out = inspect.handle_request(
        _body(_URL),
        fetch=_fetch_402(_challenge()),
        decode=_decode,
    )
    dumped = json.dumps(out)
    assert _MACAROON not in dumped
    assert _INVOICE not in dumped
    assert out == {
        "valid_challenge": True,
        "price_sats": 100,
        "expiry": 2_000_000_600,
        "payee_pubkey": _PAYEE,
        "network": "mainnet",
        "reason": "",
    }


def test_zero_amount_stays_valid() -> None:
    out = inspect.handle_request(
        _body(_URL),
        fetch=_fetch_402(_challenge()),
        decode=lambda _invoice: _Parsed(amount_msat=None),
    )
    assert out["valid_challenge"] is True
    assert out["price_sats"] is None
    assert out["reason"] == ""


def test_malformed_challenge_is_not_echoed() -> None:
    garbage = "Bearer totally-not-a-challenge"
    out = inspect.handle_request(_body(_URL), fetch=_fetch_402(garbage))
    dumped = json.dumps(out)
    assert out["valid_challenge"] is False
    assert out["price_sats"] is None
    assert out["expiry"] is None
    assert out["payee_pubkey"] is None
    assert out["network"] is None
    assert out["reason"] == "bad_challenge"
    assert "Bearer" not in dumped
    assert "totally-not-a-challenge" not in dumped


def test_missing_challenge_and_not_402() -> None:
    missing = inspect.handle_request(_body(_URL), fetch=_fetch_402(None))
    assert missing["reason"] == "missing_challenge"
    other = inspect.handle_request(
        _body(_URL),
        fetch=lambda _url: (200, _challenge(), None),
    )
    assert other["reason"] == "not_402"
    assert _INVOICE not in json.dumps(other)
    assert _MACAROON not in json.dumps(other)


def test_http_url_does_not_fetch() -> None:
    def fetch(_url: str):
        raise AssertionError("fetched")

    out = inspect.handle_request(_body("http://merchant.example/paid"), fetch=fetch)
    assert out["valid_challenge"] is False
    assert out["reason"] == "not_https"


def test_private_targets_do_not_connect() -> None:
    def fetch(_url: str):
        raise AssertionError("fetched")

    blocked = (
        "https://127.0.0.1/latest",
        "https://10.0.0.1/admin",
        "https://169.254.169.254/latest",
        "https://100.64.0.1/",
        "https://2130706433/",
    )
    for url in blocked:
        out = inspect.handle_request(_body(url), fetch=fetch)
        assert out["reason"] == "blocked_host", url
    userinfo = inspect.handle_request(
        _body("https://user:pass@merchant.example/paid"), fetch=fetch
    )
    assert userinfo["reason"] == "bad_url"


def test_dns_to_private_does_not_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    def getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 443))]

    def create_connection(*_args, **_kwargs):
        raise AssertionError("connected")

    monkeypatch.setattr(inspect.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(inspect.socket, "create_connection", create_connection)
    out = inspect.inspect("https://ok.example/paid")
    assert out["reason"] == "blocked_host"


def test_one_redirect_then_challenge() -> None:
    seen: list[str] = []

    def fetch(url: str):
        seen.append(url)
        if url.endswith("/a"):
            return 302, None, "https://merchant.example/b"
        return 402, _challenge(), None

    out = inspect.handle_request(
        _body("https://merchant.example/a"),
        fetch=fetch,
        decode=lambda _invoice: _Parsed(),
    )
    assert seen == ["https://merchant.example/a", "https://merchant.example/b"]
    assert out["valid_challenge"] is True
    assert out["price_sats"] == 100


def test_second_redirect_and_downgrade() -> None:
    def always_redirect(_url: str):
        return 302, None, "https://merchant.example/next"

    out = inspect.handle_request(_body(_URL), fetch=always_redirect)
    assert out["reason"] == "too_many_redirects"

    def downgrade(_url: str):
        return 302, None, "http://merchant.example/next"

    out = inspect.handle_request(_body(_URL), fetch=downgrade)
    assert out["reason"] == "not_https"


def test_real_bolt11_challenge() -> None:
    pytest.importorskip("bolt11")
    from bolt11 import MilliSatoshi, TagChar, Tags, encode
    from bolt11.types import Bolt11

    tags = Tags()
    tags.add(TagChar.payment_hash, "aa" * 32)
    tags.add(TagChar.payment_secret, "bb" * 32)
    tags.add(TagChar.description, "coffee")
    tags.add(TagChar.expire_time, 600)
    invoice = encode(
        Bolt11(
            currency="bc",
            date=2_000_000_000,
            tags=tags,
            amount_msat=MilliSatoshi(100_000),
        ),
        private_key="11" * 32,
    )
    macaroon = "real-challenge-macaroon-secret"
    header = f'LSAT macaroon="{macaroon}", invoice="{invoice}"'
    out = inspect.handle_request(_body(_URL), fetch=_fetch_402(header))
    dumped = json.dumps(out)
    assert macaroon not in dumped
    assert invoice not in dumped
    assert out["valid_challenge"] is True
    assert out["price_sats"] == 100
    assert out["network"] == "mainnet"
    assert out["expiry"] == 2_000_000_600
    assert out["payee_pubkey"] is not None
    assert len(out["payee_pubkey"]) == 66
    assert out["reason"] == ""


def test_bad_invoice_is_not_echoed() -> None:
    invoice = "lnbc1not-a-real-invoice"
    macaroon = "another-macaroon-secret"

    def decode(text: str) -> None:
        raise ValueError(text)

    out = inspect.handle_request(
        _body(_URL),
        fetch=_fetch_402(_challenge(macaroon, invoice)),
        decode=decode,
    )
    dumped = json.dumps(out)
    assert out["reason"] == "bad_invoice"
    assert invoice not in dumped
    assert macaroon not in dumped
    assert "ValueError" not in dumped


def test_dispatch_malformed_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(inspect, "_http_get", _fetch_402("Bearer nope"))
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=_body(_URL))
    assert status == 200
    assert content_type == "application/json"
    payload = json.loads(raw)
    assert payload["reason"] == "bad_challenge"
    assert "Bearer" not in raw.decode()
    assert "nope" not in raw.decode()


def test_missing_url_is_400() -> None:
    for body in (b"{}", b"", b"[]", b'{"url": 1}', b"not-json"):
        status, content_type, raw = dispatch(_ROUTE, method="POST", body=body)
        assert status == 400
        assert content_type == "application/json"
        assert json.loads(raw) == {"ok": False, "error": "missing_url"}


def test_get_is_405() -> None:
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/security/l402-challenge-inspect$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "l402-challenge-inspect"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    assert "https://agent-bitcoin.net/paid/security/l402-challenge-inspect" in script
    assert '"security"' in script
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "l402_challenge_inspect.py" in dockerfile
