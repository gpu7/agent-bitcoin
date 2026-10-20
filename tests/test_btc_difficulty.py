"""GET /paid/bitcoin/btc-difficulty. Mock getblockchaininfo. No node."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from l402 import btc_difficulty as diff
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-difficulty"
_HASH = "ab" * 32


def _info(**overrides: object) -> dict:
    raw = {
        "chain": "main",
        "blocks": 920000,
        "headers": 920010,
        "bestblockhash": _HASH,
        "difficulty": Decimal("1234.5"),
        "chainwork": "00AB",
        "pruned": False,
        "warnings": "secret-warning",
        "verificationprogress": Decimal("1"),
    }
    raw.update(overrides)
    return raw


def test_summary_keeps_four_fields() -> None:
    out = diff.handle_request(lambda: _info())
    assert out == {
        "difficulty": 1234.5,
        "chainwork": "00ab",
        "next_retarget_blocks": 1312,
        "blocks": 920000,
    }
    dumped = json.dumps(out)
    assert _HASH not in dumped
    assert "main" not in dumped
    assert "pruned" not in dumped
    assert "secret-warning" not in dumped


def test_whole_difficulty_is_an_integer() -> None:
    out = diff.handle_request(lambda: _info(difficulty=Decimal(1), blocks=100))
    assert out["difficulty"] == 1
    assert isinstance(out["difficulty"], int)


@pytest.mark.parametrize(
    ("height", "remaining"),
    [(2015, 1), (2016, 2016), (0, 2016)],
)
def test_next_retarget_blocks(height: int, remaining: int) -> None:
    out = diff.handle_request(lambda: _info(blocks=height))
    assert out["next_retarget_blocks"] == remaining
    assert out["blocks"] == height


def test_missing_chainwork_is_omitted() -> None:
    raw = _info()
    raw.pop("chainwork")
    out = diff.handle_request(lambda: raw)
    assert "chainwork" not in out
    assert out["blocks"] == 920000


@pytest.mark.parametrize(
    "patch",
    [
        {"chainwork": "zz"},
        {"chainwork": "0x00ab"},
        {"difficulty": True},
        {"difficulty": 0},
        {"difficulty": Decimal(0)},
        {"difficulty": "1e2"},
    ],
)
def test_bad_field_is_unavailable(patch: dict) -> None:
    with pytest.raises(diff.BitcoindUnavailable):
        diff.handle_request(lambda: _info(**patch))


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom() -> dict:
        raise RuntimeError("password=hidden")

    with pytest.raises(diff.BitcoindUnavailable) as caught:
        diff.handle_request(boom)
    assert "password=hidden" not in str(caught.value)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise diff.BitcoindUnavailable("hidden rpc text")

    monkeypatch.setattr(diff, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden rpc text" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(diff, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    peer = 'pathregexp: "^/paid/bitcoin/btc-peer-info$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-difficulty$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-difficulty"' in text
        assert needle in text
        assert text.index(peer) < text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-difficulty"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_difficulty.py" in dockerfile
