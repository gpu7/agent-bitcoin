"""GET /paid/bitcoin/btc-chain-status. Mock getblockchaininfo. No node."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from l402 import btc_chain_status as chain
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-chain-status"
_HASH = "ab" * 32


def _info(**overrides: object) -> dict:
    raw = {
        "chain": "main",
        "blocks": 920000,
        "headers": 920010,
        "bestblockhash": _HASH,
        "verificationprogress": Decimal("0.999"),
        "initialblockdownload": False,
        "pruned": True,
        "pruneheight": 780000,
        "warnings": "secret-warning",
        "size_on_disk": 123,
    }
    raw.update(overrides)
    return raw


def test_pruned_summary_drops_extra_fields() -> None:
    out = chain.handle_request(lambda: _info())
    assert out == {
        "blocks": 920000,
        "headers": 920010,
        "verificationprogress": float(Decimal("0.999")),
        "initialblockdownload": False,
        "chain": "main",
        "pruned": True,
        "pruneheight": 780000,
    }
    dumped = json.dumps(out)
    assert _HASH not in dumped
    assert "secret-warning" not in dumped
    assert "size_on_disk" not in dumped


def test_unpruned_omits_pruneheight() -> None:
    out = chain.handle_request(
        lambda: _info(
            pruned=False,
            pruneheight=1,
            verificationprogress=Decimal(1),
            chain="regtest",
        )
    )
    assert "pruneheight" not in out
    assert out["pruned"] is False
    assert out["verificationprogress"] == 1
    assert out["chain"] == "regtest"


def test_bad_chain_or_blocks_is_unavailable() -> None:
    with pytest.raises(chain.BitcoindUnavailable):
        chain.handle_request(lambda: _info(chain="secret-net"))
    with pytest.raises(chain.BitcoindUnavailable):
        chain.handle_request(lambda: _info(blocks=True))


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom() -> dict:
        raise RuntimeError("password=hidden")

    with pytest.raises(chain.BitcoindUnavailable):
        chain.handle_request(boom)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise chain.BitcoindUnavailable("hidden")

    monkeypatch.setattr(chain, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("rpc")

    monkeypatch.setattr(chain, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_register_script_and_image() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/bitcoin/btc-chain-status$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-chain-status"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-chain-status"
    assert url in script
    window = script[script.index(url) : script.index(url) + 400]
    assert "bitcoin" in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_chain_status.py" in dockerfile
