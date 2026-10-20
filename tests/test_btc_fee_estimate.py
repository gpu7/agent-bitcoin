"""GET /paid/bitcoin/btc-fee-estimate. Mock estimatesmartfee results. No node."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from l402 import btc_fee_estimate as fee
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-fee-estimate"


def _caller(results: dict[int, dict]):
    def call(target: int) -> dict:
        if target not in results:
            raise fee.BitcoindUnavailable("secret-host")
        return results[target]

    return call


def test_converts_btc_per_kvb_and_keeps_core_blocks() -> None:
    out = fee.handle_request(
        _caller(
            {
                1: {"feerate": Decimal("0.00001000"), "blocks": 2},
                3: {"feerate": Decimal("0.00001234"), "blocks": 3},
                6: {"feerate": Decimal("0.00020000"), "blocks": 6},
            }
        )
    )
    assert out["estimates"] == [
        {"blocks": 2, "feerate_sats_per_vb": 1},
        {"blocks": 3, "feerate_sats_per_vb": 1.23},
        {"blocks": 6, "feerate_sats_per_vb": 20},
    ]


def test_missing_estimate_is_a_note_without_core_text() -> None:
    out = fee.handle_request(
        _caller(
            {
                1: {"feerate": Decimal("0.00001000"), "blocks": 1},
                3: {
                    "errors": ["Insufficient data or no feerate found"],
                    "blocks": 3,
                },
                6: {"feerate": True, "blocks": 6},
            }
        )
    )
    assert out["estimates"][1] == {
        "blocks": 3,
        "feerate_sats_per_vb": None,
        "note": "estimate_unavailable",
    }
    assert out["estimates"][2]["note"] == "estimate_unavailable"
    raw = json.dumps(out)
    assert "Insufficient" not in raw
    assert "secret" not in raw


def test_transport_error_does_not_return_a_partial_body() -> None:
    def call(target: int) -> dict:
        if target == 1:
            return {"feerate": Decimal("0.00001000"), "blocks": 1}
        raise RuntimeError("password=hidden")

    with pytest.raises(fee.BitcoindUnavailable):
        fee.handle_request(call)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise fee.BitcoindUnavailable("hidden")

    monkeypatch.setattr(fee, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("rpc")

    monkeypatch.setattr(fee, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_register_script_and_image() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/bitcoin/btc-fee-estimate$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-fee-estimate"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-fee-estimate"
    assert url in script
    window = script[script.index(url) : script.index(url) + 400]
    assert "bitcoin" in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_fee_estimate.py" in dockerfile
