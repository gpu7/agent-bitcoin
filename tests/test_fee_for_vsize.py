"""ABT-L402-008 — fee-for-vsize uses feerate cache; vbytes not weight."""

from __future__ import annotations

import json

import pytest

from l402 import fee_for_vsize as ffv
from l402 import mempool_feerate as mf
from l402.origin import dispatch

_RATES = {
    "ok": True,
    "service": "mempool-feerate",
    "version": "v1",
    "as_of": "2026-09-07T17:00:00Z",
    "ttl_s": 30,
    "unit": "sat_per_vbyte",
    "fast": 12,
    "medium": 8,
    "slow": 3,
    "source": "public_mempool_api",
    "source_as_of": "2026-09-07T16:59:50Z",
    "stale": False,
}


def test_compute_250vb_ceils() -> None:
    out = ffv.compute(250, _RATES)
    assert out["vsize"] == 250
    assert out["fee_sats_fast"] == 3000
    assert out["fee_sats_medium"] == 2000
    assert out["fee_sats_slow"] == 750
    assert out["as_of"] == _RATES["as_of"]
    assert out["ttl_s"] == 30
    assert out["source"] == "public_mempool_api"
    assert out["stale"] is False
    assert out["service"] == "fee-for-vsize"
    for key in ("fast", "medium", "slow", "unit"):
        assert key not in out


def test_parse_rejects_bounds_and_weight() -> None:
    with pytest.raises(ffv.BadVsize):
        ffv.parse_vsize("vsize=109")
    with pytest.raises(ffv.BadVsize):
        ffv.parse_vsize("vsize=100001")
    with pytest.raises(ffv.BadVsize):
        ffv.parse_vsize("")
    with pytest.raises(ffv.BadVsize):
        ffv.parse_vsize("weight=250")
    with pytest.raises(ffv.BadVsize):
        ffv.parse_vsize("vsize=250.5")
    with pytest.raises(ffv.BadVsize):
        ffv.parse_vsize("vsize=250&weight=1")
    assert ffv.parse_vsize("vsize=110") == 110
    assert ffv.parse_vsize("vsize=100000") == 100000


def test_dispatch_200_uses_feerate_quote(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_quote(**_k):
        calls["n"] += 1
        return dict(_RATES)

    monkeypatch.setattr(mf, "get_quote", fake_quote)
    status, ctype, body = dispatch("/paid/finance/fee-for-vsize?vsize=250")
    assert status == 200
    assert ctype == "application/json"
    data = json.loads(body)
    assert data["fee_sats_fast"] == 3000
    assert data["fee_sats_medium"] == 2000
    assert data["fee_sats_slow"] == 750
    assert calls["n"] == 1


def test_dispatch_400_bad_vsize() -> None:
    for path in (
        "/paid/finance/fee-for-vsize",
        "/paid/finance/fee-for-vsize?vsize=109",
        "/paid/finance/fee-for-vsize?vsize=100001",
        "/paid/finance/fee-for-vsize?weight=250",
    ):
        status, ctype, body = dispatch(path)
        assert status == 400
        assert ctype == "application/json"
        assert json.loads(body) == {"ok": False, "error": "bad_vsize"}


def test_dispatch_503_empty_feerate_cache(monkeypatch) -> None:
    def boom(**_k):
        raise mf.UpstreamUnavailable("down")

    monkeypatch.setattr(mf, "get_quote", boom)
    status, ctype, body = dispatch("/paid/finance/fee-for-vsize?vsize=250")
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": "upstream_unavailable"}
