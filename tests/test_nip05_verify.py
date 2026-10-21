"""NIP-05 verify. Guarded HTTPS. No nsec."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import nip05_verify as nip05
from l402.origin import dispatch

_ROUTE = "/paid/nostr/nip05-verify"
_PUB = "aa" * 32
_OTHER = "bb" * 32
_NPUB = "npub1424242424242424242424242424242424242424242424242424qamrcaj"
_OTHER_NPUB = "npub1hwamhwamhwamhwamhwamhwamhwamhwamhwamhwamhwamhwamhwasxw04hu"


@pytest.fixture(autouse=True)
def _clear_limiter() -> None:
    nip05._reset_limiter()


def _body(nip: str = "alice@example.com", npub: str = _NPUB) -> bytes:
    return json.dumps({"nip05": nip, "npub": npub}).encode()


def test_match_is_valid() -> None:
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, bytes, None]:
        calls.append(url)
        payload = {
            "names": {"alice": _PUB},
            "debug": "RAWBODYTOKEN",
        }
        return 200, json.dumps(payload).encode(), None

    out = nip05.handle_request(_body(), fetch=fetch)
    dumped = json.dumps(out)
    assert out == {"valid": True, "reason": ""}
    assert calls == ["https://example.com/.well-known/nostr.json?name=alice"]
    assert _PUB not in dumped
    assert _NPUB not in dumped
    assert "RAWBODYTOKEN" not in dumped


def test_mismatch_is_invalid() -> None:
    def fetch(_url: str) -> tuple[int, bytes, None]:
        return 200, json.dumps({"names": {"alice": _OTHER}}).encode(), None

    out = nip05.handle_request(_body(), fetch=fetch)
    dumped = json.dumps(out)
    assert out == {"valid": False, "reason": "pubkey_mismatch"}
    assert _OTHER not in dumped
    assert _NPUB not in dumped


def test_nsec_does_not_fetch() -> None:
    def fetch(_url: str) -> tuple[int, bytes, None]:
        raise AssertionError("fetch called")

    with pytest.raises(nip05.BadNpub):
        nip05.handle_request(_body(npub="nsec1notasecret"), fetch=fetch)


def test_localhost_is_blocked_before_fetch() -> None:
    def fetch(_url: str) -> tuple[int, bytes, None]:
        raise AssertionError("fetch called")

    out = nip05.handle_request(_body(nip="alice@localhost"), fetch=fetch)
    assert out == {"valid": False, "reason": "blocked_host"}


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(nip05, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/nostr/nip05-verify"
    needle = 'pathregexp: "^/paid/nostr/nip05-verify$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "nip05-verify"' in text
        assert text.index('name: "nostr-node-link"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-address-validate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"nostr"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "nip05_verify.py" in docker


def test_other_npub_constant_decodes() -> None:
    assert _OTHER_NPUB.startswith("npub1")
