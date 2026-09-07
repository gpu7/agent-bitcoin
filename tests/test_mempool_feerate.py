"""ABT-L402-006 — mempool-feerate digest, cache, and origin JSON."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from l402 import mempool_feerate as mf
from l402.origin import dispatch

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "mempool_fees_recommended.json"
)
_FIXED_NOW = datetime(2026, 9, 7, 14, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def recommended() -> dict:
    return json.loads(_FIXTURE.read_text())


@pytest.fixture(autouse=True)
def _reset_feerate_cache():
    mf.reset_cache()
    yield
    mf.reset_cache()


def test_digest_maps_recommended_bands(recommended: dict) -> None:
    out = mf.digest_recommended(recommended, now=_FIXED_NOW, ttl_s=30)
    assert out["ok"] is True
    assert out["service"] == "mempool-feerate"
    assert out["version"] == "v1"
    assert out["unit"] == "sat_per_vbyte"
    assert out["fast"] == 12
    assert out["medium"] == 8
    assert out["slow"] == 3
    assert out["ttl_s"] == 30
    assert out["as_of"] == "2026-09-07T14:00:00Z"
    assert out["source_as_of"] == "2026-09-07T14:00:00Z"
    assert out["stale"] is False
    assert out["source"] == "public_mempool_api"
    for key in ("fast", "medium", "slow"):
        assert isinstance(out[key], int)
        assert out[key] >= 1


def test_digest_clamps_sub_one_to_one() -> None:
    raw = {"fastestFee": 0, "halfHourFee": 0.4, "hourFee": 0}
    out = mf.digest_recommended(raw, now=_FIXED_NOW)
    assert out["fast"] == 1
    assert out["medium"] == 1
    assert out["slow"] == 1


def test_cache_hit_does_not_refetch(recommended: dict) -> None:
    calls = {"n": 0}

    def fetch(_url: str) -> dict:
        calls["n"] += 1
        return recommended

    mono = {"t": 0.0}

    def clock() -> float:
        return mono["t"]

    a = mf.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=clock)
    b = mf.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=clock)
    assert calls["n"] == 1
    assert a == b
    assert a["stale"] is False


def test_ttl_expiry_refetches(recommended: dict) -> None:
    calls = {"n": 0}

    def fetch(_url: str) -> dict:
        calls["n"] += 1
        return dict(recommended, fastestFee=10 + calls["n"])

    mono = {"t": 0.0}

    def clock() -> float:
        return mono["t"]

    first = mf.get_quote(fetch=fetch, ttl_s=15, now=_FIXED_NOW, monotonic=clock)
    assert first["fast"] == 11
    mono["t"] = 16.0
    second = mf.get_quote(fetch=fetch, ttl_s=15, now=_FIXED_NOW, monotonic=clock)
    assert calls["n"] == 2
    assert second["fast"] == 12


def test_upstream_fail_with_cache_returns_stale(recommended: dict) -> None:
    def ok(_url: str) -> dict:
        return recommended

    mf.get_quote(fetch=ok, ttl_s=15, now=_FIXED_NOW, monotonic=lambda: 0.0)

    def boom(_url: str) -> dict:
        raise OSError("timeout")

    out = mf.get_quote(fetch=boom, ttl_s=15, now=_FIXED_NOW, monotonic=lambda: 20.0)
    assert out["stale"] is True
    assert out["fast"] == 12
    assert out["ok"] is True


def test_upstream_fail_without_cache_raises() -> None:
    def boom(_url: str) -> dict:
        raise OSError("down")

    with pytest.raises(mf.UpstreamUnavailable):
        mf.get_quote(fetch=boom, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)


def test_origin_dispatch_200_json(monkeypatch, recommended: dict) -> None:
    monkeypatch.setattr(
        mf, "get_quote", lambda **_k: mf.digest_recommended(recommended, now=_FIXED_NOW)
    )
    status, content_type, body = dispatch("/paid/finance/mempool-feerate")
    assert status == 200
    assert content_type == "application/json"
    data = json.loads(body)
    for key in (
        "ok",
        "service",
        "version",
        "as_of",
        "ttl_s",
        "unit",
        "fast",
        "medium",
        "slow",
        "source",
        "source_as_of",
        "stale",
    ):
        assert key in data
    assert data["ok"] is True
    assert data["fast"] == 12


def test_origin_dispatch_503_without_cache(monkeypatch) -> None:
    def boom(**_k):
        raise mf.UpstreamUnavailable("down")

    monkeypatch.setattr(mf, "get_quote", boom)
    status, content_type, body = dispatch("/paid/finance/mempool-feerate")
    assert status == 503
    assert content_type == "application/json"
    data = json.loads(body)
    assert data == {"ok": False, "error": "upstream_unavailable"}


@pytest.mark.skipif(
    os.getenv("MEMPOOL_FEERATE_LIVE") != "1", reason="set MEMPOOL_FEERATE_LIVE=1"
)
def test_live_public_endpoint() -> None:
    mf.reset_cache()
    quote = mf.get_quote()
    assert quote["fast"] >= 1
    assert quote["medium"] >= 1
    assert quote["slow"] >= 1
