"""ABT-L402-010 — btc-usd digest, cache, and origin JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from l402 import btc_usd as bu
from l402.origin import dispatch

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "btc_usd_prices.json"
_FIXED_NOW = datetime(2026, 9, 7, 17, 50, 0, tzinfo=timezone.utc)


@pytest.fixture
def prices() -> dict:
    return json.loads(_FIXTURE.read_text())


@pytest.fixture(autouse=True)
def _reset_btc_usd_cache():
    bu.reset_cache()
    yield
    bu.reset_cache()


def test_digest_fixture(prices: dict) -> None:
    out = bu.digest_prices(prices, now=_FIXED_NOW, ttl_s=30)
    assert out["btc_usd"] == 100000
    assert out["sats_per_usd"] == 1000
    assert out["service"] == "btc-usd"
    assert out["source"] == "public_price_api"
    assert out["stale"] is False
    assert out["as_of"] == "2026-09-07T17:50:00Z"
    assert out["source_as_of"] == "2026-09-07T17:50:08Z"
    assert "btc_sats" not in out
    assert "EUR" not in out
    assert "time" not in out


def test_digest_float_usd() -> None:
    out = bu.digest_prices({"USD": 97450.12}, now=_FIXED_NOW, ttl_s=30)
    assert out["btc_usd"] == 97450.12
    assert out["sats_per_usd"] == 1026
    assert isinstance(out["sats_per_usd"], int)


def test_ttl_clamp(monkeypatch) -> None:
    monkeypatch.setenv("BTC_USD_TTL_S", "15")
    assert bu.ttl_s_from_env() == 30
    monkeypatch.setenv("BTC_USD_TTL_S", "90")
    assert bu.ttl_s_from_env() == 60
    monkeypatch.delenv("BTC_USD_TTL_S", raising=False)
    assert bu.ttl_s_from_env() == 30


def test_cache_hit_does_not_refetch(prices: dict) -> None:
    calls = {"n": 0}

    def fetch(_url: str) -> dict:
        calls["n"] += 1
        return prices

    a = bu.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)
    b = bu.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)
    assert calls["n"] == 1
    assert a == b


def test_ttl_expiry_refetches(prices: dict) -> None:
    calls = {"n": 0}

    def fetch(_url: str) -> dict:
        calls["n"] += 1
        return dict(prices, USD=100000 + calls["n"])

    mono = {"t": 0.0}

    def clock() -> float:
        return mono["t"]

    first = bu.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=clock)
    assert first["btc_usd"] == 100001
    mono["t"] = 31.0
    second = bu.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=clock)
    assert calls["n"] == 2
    assert second["btc_usd"] == 100002


def test_fail_with_cache_stale(prices: dict) -> None:
    bu.get_quote(
        fetch=lambda _u: prices, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0
    )

    def boom(_url: str) -> dict:
        raise OSError("timeout")

    out = bu.get_quote(fetch=boom, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 40.0)
    assert out["stale"] is True
    assert out["sats_per_usd"] == 1000


def test_fail_without_cache_raises() -> None:
    def boom(_url: str) -> dict:
        raise OSError("down")

    with pytest.raises(bu.UpstreamUnavailable):
        bu.get_quote(fetch=boom, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)


def test_unusable_usd_without_cache_raises() -> None:
    with pytest.raises(bu.UpstreamUnavailable):
        bu.get_quote(
            fetch=lambda _u: {"EUR": 1},
            ttl_s=30,
            now=_FIXED_NOW,
            monotonic=lambda: 0.0,
        )
    with pytest.raises(bu.UpstreamUnavailable):
        bu.get_quote(
            fetch=lambda _u: {"USD": 0},
            ttl_s=30,
            now=_FIXED_NOW,
            monotonic=lambda: 0.0,
        )
    with pytest.raises(bu.UpstreamUnavailable):
        bu.get_quote(
            fetch=lambda _u: {"USD": -1},
            ttl_s=30,
            now=_FIXED_NOW,
            monotonic=lambda: 0.0,
        )
    with pytest.raises(bu.UpstreamUnavailable):
        bu.get_quote(
            fetch=lambda _u: {"USD": None},
            ttl_s=30,
            now=_FIXED_NOW,
            monotonic=lambda: 0.0,
        )


def test_origin_dispatch_200(monkeypatch, prices: dict) -> None:
    monkeypatch.setattr(
        bu, "get_quote", lambda **_k: bu.digest_prices(prices, now=_FIXED_NOW)
    )
    status, ctype, body = dispatch("/paid/finance/btc-usd")
    assert status == 200
    assert ctype == "application/json"
    data = json.loads(body)
    assert data["btc_usd"] == 100000
    assert data["sats_per_usd"] == 1000


def test_origin_dispatch_503(monkeypatch) -> None:
    def boom(**_k):
        raise bu.UpstreamUnavailable("down")

    monkeypatch.setattr(bu, "get_quote", boom)
    status, _ctype, body = dispatch("/paid/finance/btc-usd")
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": "upstream_unavailable"}
