"""GET /paid/bitcoin/btc-block-tip. Mock getblockchaininfo. No node."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from l402 import btc_block_tip as tip
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-block-tip"
_HASH = "ab" * 32


def _info(**overrides: object) -> dict:
    raw = {
        "chain": "main",
        "blocks": 920000,
        "headers": 920010,
        "bestblockhash": _HASH.upper(),
        "mediantime": 1_700_000_000,
        "difficulty": Decimal("1234.5"),
        "chainwork": "00ab",
        "pruned": False,
        "warnings": "secret-warning",
        "time": 1_700_000_100,
    }
    raw.update(overrides)
    return raw


def test_tip_keeps_three_fields() -> None:
    out = tip.handle_request(lambda: _info())
    assert out == {
        "height": 920000,
        "best_block_hash": _HASH,
        "median_time": 1_700_000_000,
    }
    dumped = json.dumps(out)
    assert "1234.5" not in dumped
    assert "00ab" not in dumped
    assert "pruned" not in dumped
    assert "secret-warning" not in dumped
    assert "1700000100" not in dumped


def test_missing_mediantime_is_omitted() -> None:
    raw = _info()
    raw.pop("mediantime")
    out = tip.handle_request(lambda: raw)
    assert out == {"height": 920000, "best_block_hash": _HASH}
    assert "median_time" not in out


@pytest.mark.parametrize(
    "patch",
    [
        {"bestblockhash": "ab" * 31},
        {"bestblockhash": "0x" + "ab" * 31},
        {"bestblockhash": "zz" * 32},
        {"blocks": True},
        {"mediantime": Decimal("1.5")},
        {"mediantime": "soon"},
    ],
)
def test_bad_field_is_unavailable(patch: dict) -> None:
    with pytest.raises(tip.BitcoindUnavailable):
        tip.handle_request(lambda: _info(**patch))


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom() -> dict:
        raise RuntimeError("password=hidden")

    with pytest.raises(tip.BitcoindUnavailable) as caught:
        tip.handle_request(boom)
    assert "password=hidden" not in str(caught.value)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise tip.BitcoindUnavailable("hidden rpc text")

    monkeypatch.setattr(tip, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden rpc text" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(tip, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    difficulty = 'pathregexp: "^/paid/bitcoin/btc-difficulty$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-block-tip$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-block-tip"' in text
        assert needle in text
        assert (
            text.index(difficulty)
            < text.index(needle)
            < text.index('name: "l402-demo"')
        )
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-block-tip"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_block_tip.py" in dockerfile
