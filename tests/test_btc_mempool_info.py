"""GET /paid/bitcoin/btc-mempool-info. Mock getmempoolinfo. No node."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from l402 import btc_mempool_info as pool
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-mempool-info"


def _raw(**overrides: object) -> dict:
    body = {
        "size": 1200,
        "bytes": 4_500_000,
        "usage": 6_700_000,
        "total_fee": Decimal("0.015"),
        "mempoolminfee": Decimal("0.00001"),
        "maxmempool": 300_000_000,
        "fullrbf": False,
    }
    body.update(overrides)
    return body


def test_summary_keeps_core_units_and_drops_extra_fields() -> None:
    out = pool.handle_request(lambda: _raw())
    assert out["size"] == 1200
    assert out["bytes"] == 4_500_000
    assert out["usage"] == 6_700_000
    assert out["total_fee"] == float(Decimal("0.015"))
    assert out["mempoolminfee"] == float(Decimal("0.00001"))
    dumped = json.dumps(out)
    assert "fullrbf" not in dumped
    assert "maxmempool" not in dumped


def test_missing_total_fee_omits_the_key() -> None:
    raw = _raw()
    del raw["total_fee"]
    out = pool.handle_request(lambda: raw)
    assert "total_fee" not in out
    assert out["size"] == 1200
    assert out["mempoolminfee"] == float(Decimal("0.00001"))


def test_bad_size_or_min_fee_is_unavailable() -> None:
    with pytest.raises(pool.BitcoindUnavailable):
        pool.handle_request(lambda: _raw(size=True))
    with pytest.raises(pool.BitcoindUnavailable):
        pool.handle_request(lambda: _raw(mempoolminfee=Decimal("-0.00001")))


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom() -> dict:
        raise RuntimeError("password=hidden")

    with pytest.raises(pool.BitcoindUnavailable):
        pool.handle_request(boom)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise pool.BitcoindUnavailable("hidden")

    monkeypatch.setattr(pool, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("rpc")

    monkeypatch.setattr(pool, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_register_script_and_image() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/bitcoin/btc-mempool-info$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-mempool-info"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-info"
    assert url in script
    window = script[script.index(url) : script.index(url) + 400]
    assert "bitcoin" in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_mempool_info.py" in dockerfile
