"""ABT-L402-007 — mempool-backlog digest, cache, and origin JSON."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from l402 import mempool_backlog as mb
from l402.origin import dispatch

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mempool_backlog.json"
_FIXED_NOW = datetime(2026, 9, 7, 16, 0, 0, tzinfo=timezone.utc)
_BANDS = ("fast", "medium", "slow")


@pytest.fixture
def mempool_raw() -> dict:
    return json.loads(_FIXTURE.read_text())


@pytest.fixture(autouse=True)
def _reset_backlog_cache():
    mb.reset_cache()
    yield
    mb.reset_cache()


def test_digest_maps_mempool_counts(mempool_raw: dict) -> None:
    out = mb.digest_mempool(mempool_raw, now=_FIXED_NOW, ttl_s=30)
    assert out["ok"] is True
    assert out["service"] == "mempool-backlog"
    assert out["version"] == "v1"
    assert out["tx_count"] == 45210
    assert out["vsize"] == 183204441
    assert out["total_fee_sats"] == 125000000
    assert out["vsize_per_block_equiv"] == pytest.approx(183.204441)
    assert out["ttl_s"] == 30
    assert out["as_of"] == "2026-09-07T16:00:00Z"
    assert out["stale"] is False
    for key in _BANDS:
        assert key not in out


def test_digest_omits_total_fee_when_absent() -> None:
    out = mb.digest_mempool({"count": 1, "vsize": 0}, now=_FIXED_NOW)
    assert "total_fee_sats" not in out
    assert out["tx_count"] == 1
    assert out["vsize"] == 0


def test_cache_hit_does_not_refetch(mempool_raw: dict) -> None:
    calls = {"n": 0}

    def fetch(_url: str) -> dict:
        calls["n"] += 1
        return mempool_raw

    first = mb.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)
    second = mb.get_quote(fetch=fetch, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)
    assert calls["n"] == 1
    assert first == second


def test_ttl_expiry_refetches(mempool_raw: dict) -> None:
    calls = {"n": 0}

    def fetch(_url: str) -> dict:
        calls["n"] += 1
        return dict(mempool_raw, count=calls["n"])

    mono = {"t": 0.0}

    def clock() -> float:
        return mono["t"]

    first = mb.get_quote(fetch=fetch, ttl_s=15, now=_FIXED_NOW, monotonic=clock)
    assert first["tx_count"] == 1
    mono["t"] = 16.0
    second = mb.get_quote(fetch=fetch, ttl_s=15, now=_FIXED_NOW, monotonic=clock)
    assert calls["n"] == 2
    assert second["tx_count"] == 2


def test_upstream_fail_with_cache_returns_stale(mempool_raw: dict) -> None:
    mb.get_quote(
        fetch=lambda _u: mempool_raw, ttl_s=15, now=_FIXED_NOW, monotonic=lambda: 0.0
    )

    def boom(_url: str) -> dict:
        raise OSError("timeout")

    out = mb.get_quote(fetch=boom, ttl_s=15, now=_FIXED_NOW, monotonic=lambda: 20.0)
    assert out["stale"] is True
    assert out["tx_count"] == 45210
    assert out["ok"] is True


def test_upstream_fail_without_cache_raises() -> None:
    def boom(_url: str) -> dict:
        raise OSError("down")

    with pytest.raises(mb.UpstreamUnavailable):
        mb.get_quote(fetch=boom, ttl_s=30, now=_FIXED_NOW, monotonic=lambda: 0.0)


def test_origin_dispatch_200_json(monkeypatch, mempool_raw: dict) -> None:
    monkeypatch.setattr(
        mb, "get_quote", lambda **_k: mb.digest_mempool(mempool_raw, now=_FIXED_NOW)
    )
    status, content_type, body = dispatch("/paid/finance/mempool-backlog")
    assert status == 200
    assert content_type == "application/json"
    data = json.loads(body)
    for key in (
        "ok",
        "service",
        "version",
        "as_of",
        "ttl_s",
        "tx_count",
        "vsize",
        "vsize_per_block_equiv",
        "source",
        "source_as_of",
        "stale",
    ):
        assert key in data
    assert data["tx_count"] == 45210
    assert data["total_fee_sats"] == 125000000
    for key in _BANDS:
        assert key not in data


def test_origin_dispatch_503_without_cache(monkeypatch) -> None:
    def boom(**_k):
        raise mb.UpstreamUnavailable("down")

    monkeypatch.setattr(mb, "get_quote", boom)
    status, content_type, body = dispatch("/paid/finance/mempool-backlog")
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": "upstream_unavailable"}


@pytest.mark.skipif(
    os.getenv("MEMPOOL_BACKLOG_LIVE") != "1", reason="set MEMPOOL_BACKLOG_LIVE=1"
)
def test_live_public_endpoint() -> None:
    mb.reset_cache()
    quote = mb.get_quote()
    assert quote["tx_count"] >= 0
    assert quote["vsize"] >= 0
