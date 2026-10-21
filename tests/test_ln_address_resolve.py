"""Lightning address metadata. One LNURL pay document. No invoice request."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_address_resolve as address
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-address-resolve"
_CALLBACK = "https://pay.example.com/lnurlp/alice/invoice"
_PUB = "ab" * 32


@pytest.fixture(autouse=True)
def _clear_limiter() -> None:
    address._reset_limiter()


def _remote() -> dict:
    metadata = json.dumps(
        [["text/plain", "Coffee"], ["text/identifier", "alice@example.com"]]
    )
    return {
        "tag": "payRequest",
        "callback": _CALLBACK,
        "minSendable": 100_000,
        "maxSendable": 100_000_000,
        "metadata": metadata,
        "nostrPubkey": _PUB,
        "comment": "RAWBODYTOKEN",
    }


def test_returns_range_without_requesting_callback() -> None:
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, bytes, None]:
        calls.append(url)
        return 200, json.dumps(_remote()).encode(), None

    body = json.dumps({"address": "alice@example.com"}).encode()
    out = address.handle_request(body, fetch=fetch)
    dumped = json.dumps(out)
    assert out["min_sats"] == 100
    assert out["max_sats"] == 100_000
    assert out["description"] == "Coffee"
    assert out["callback_domain"] == "pay.example.com"
    assert "reason" not in out
    assert calls == ["https://example.com/.well-known/lnurlp/alice"]
    assert _CALLBACK not in calls
    assert _CALLBACK not in dumped
    assert "RAWBODYTOKEN" not in dumped
    assert _PUB not in dumped
    assert "text/identifier" not in dumped


def test_slash_in_user_is_400_before_fetch() -> None:
    def fetch(_url: str) -> tuple[int, bytes, None]:
        raise AssertionError("fetch called")

    body = json.dumps({"address": "ali/ce@example.com"}).encode()
    with pytest.raises(address.BadInput):
        address.handle_request(body, fetch=fetch)


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(address, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-address-resolve"
    needle = 'pathregexp: "^/paid/lightning/ln-address-resolve$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-address-resolve"' in text
        assert text.index('name: "ln-invoice-create"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 450]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_address_resolve.py" in docker
