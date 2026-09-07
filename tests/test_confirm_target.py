"""ABT-L402-009 — confirm-target snaps minutes to feerate bands."""

from __future__ import annotations

import json

import pytest

from l402 import confirm_target as ct
from l402 import fee_for_vsize as ffv
from l402 import mempool_feerate as mf
from l402.origin import dispatch

_RATES = {
    "ok": True,
    "service": "mempool-feerate",
    "version": "v1",
    "as_of": "2026-09-07T17:20:00Z",
    "ttl_s": 30,
    "unit": "sat_per_vbyte",
    "fast": 12,
    "medium": 8,
    "slow": 3,
    "source": "public_mempool_api",
    "source_as_of": "2026-09-07T17:19:50Z",
    "stale": False,
}


@pytest.mark.parametrize(
    ("minutes", "target"),
    [
        (1, "fast"),
        (10, "fast"),
        (20, "fast"),
        (21, "medium"),
        (45, "medium"),
        (46, "slow"),
        (60, "slow"),
    ],
)
def test_snap_minutes(minutes: int, target: str) -> None:
    assert ct.snap_minutes(minutes) == target


def test_parse_minutes_and_target() -> None:
    assert ct.parse_request("minutes=10")[0] == "fast"
    assert ct.parse_request("minutes=21")[0] == "medium"
    assert ct.parse_request("minutes=60")[0] == "slow"
    t, minutes, vsize = ct.parse_request("target=slow")
    assert t == "slow"
    assert minutes is None
    assert vsize is None
    t, minutes, _ = ct.parse_request("minutes=30&target=medium")
    assert t == "medium"
    assert minutes == 30


def test_parse_rejects_bad_params() -> None:
    with pytest.raises(ct.BadConfirmTarget):
        ct.parse_request("minutes=0")
    with pytest.raises(ct.BadConfirmTarget):
        ct.parse_request("minutes=61")
    with pytest.raises(ct.BadConfirmTarget):
        ct.parse_request("")
    with pytest.raises(ct.BadConfirmTarget):
        ct.parse_request("minutes=30&target=fast")
    with pytest.raises(ffv.BadVsize):
        ct.parse_request("minutes=30&vsize=109")
    with pytest.raises(ffv.BadVsize):
        ct.parse_request("target=fast&weight=250")


def test_compute_optional_vsize() -> None:
    out = ct.compute("medium", _RATES, minutes=30, vsize=250)
    assert out["target"] == "medium"
    assert out["minutes"] == 30
    assert out["sat_vb"] == 8
    assert out["vsize"] == 250
    assert out["fee_sats"] == 2000
    named = ct.compute("slow", _RATES)
    assert "minutes" not in named
    assert "vsize" not in named
    assert "fee_sats" not in named
    assert named["sat_vb"] == 3


def test_dispatch_200(monkeypatch) -> None:
    monkeypatch.setattr(mf, "get_quote", lambda **_k: dict(_RATES))
    status, _ctype, body = dispatch("/paid/finance/confirm-target?minutes=30")
    assert status == 200
    data = json.loads(body)
    assert data["target"] == "medium"
    assert data["minutes"] == 30
    assert data["sat_vb"] == 8
    assert "fee_sats" not in data

    status, _ctype, body = dispatch("/paid/finance/confirm-target?target=slow")
    data = json.loads(body)
    assert status == 200
    assert data["target"] == "slow"
    assert "minutes" not in data

    status, _ctype, body = dispatch(
        "/paid/finance/confirm-target?minutes=30&target=medium&vsize=250"
    )
    data = json.loads(body)
    assert data["fee_sats"] == 2000
    assert data["vsize"] == 250


def test_dispatch_400() -> None:
    for path in (
        "/paid/finance/confirm-target",
        "/paid/finance/confirm-target?minutes=0",
        "/paid/finance/confirm-target?minutes=61",
        "/paid/finance/confirm-target?minutes=30&target=fast",
        "/paid/finance/confirm-target?minutes=30&vsize=109",
        "/paid/finance/confirm-target?target=fast&weight=1",
    ):
        status, _ctype, body = dispatch(path)
        assert status == 400
        err = json.loads(body)["error"]
        assert err in ("bad_confirm_target", "bad_vsize")


def test_dispatch_503(monkeypatch) -> None:
    def boom(**_k):
        raise mf.UpstreamUnavailable("down")

    monkeypatch.setattr(mf, "get_quote", boom)
    status, _ctype, body = dispatch("/paid/finance/confirm-target?minutes=30")
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": "upstream_unavailable"}
