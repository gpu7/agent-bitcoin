"""Read-only LND channel summary. No live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_channel_stats as stats
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-channel-stats"
_POINT = "ab" * 32 + ":0"
_PUBKEY = "02" + "cd" * 32


class _Reader:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def list_channels(self) -> dict:
        self.calls += 1
        return self.payload


def _channels() -> dict:
    return {
        "channels": [
            {
                "active": True,
                "capacity": "500000",
                "local_balance": "200000",
                "remote_balance": "300000",
                "channel_point": _POINT,
                "peer_alias": "mac-peer",
                "remote_pubkey": _PUBKEY,
                "pending_htlcs": [{"hash_lock": "secret-htlc"}],
            },
            {
                "active": False,
                "capacity": "100000",
                "local_balance": "1000",
                "remote_balance": "99000",
                "channel_point": "11" * 32 + ":1",
                "peer_alias": "idle",
                "remote_pubkey": "03" + "ee" * 32,
            },
        ]
    }


def test_active_and_inactive_totals() -> None:
    reader = _Reader(_channels())
    out = stats.handle_request(reader)
    dumped = json.dumps(out)
    assert out == {
        "num_active": 1,
        "num_inactive": 1,
        "total_capacity_sats": 600_000,
        "total_local_balance_sats": 201_000,
        "total_remote_balance_sats": 399_000,
        "channels": [{"channel_point": _POINT, "peer_alias": "mac-peer"}],
    }
    assert _PUBKEY not in dumped
    assert "secret-htlc" not in dumped
    assert "pending_htlcs" not in dumped
    assert "remote_pubkey" not in dumped
    assert reader.calls == 1


def test_omitted_active_is_inactive() -> None:
    out = stats.handle_request(
        _Reader(
            {
                "channels": [
                    {
                        "capacity": "1000",
                        "local_balance": "1",
                        "remote_balance": "2",
                    }
                ]
            }
        )
    )
    assert out["num_active"] == 0
    assert out["num_inactive"] == 1
    assert out["channels"] == []


def test_empty_channels() -> None:
    out = stats.handle_request(_Reader({"channels": []}))
    assert out == {
        "num_active": 0,
        "num_inactive": 0,
        "total_capacity_sats": 0,
        "total_local_balance_sats": 0,
        "total_remote_balance_sats": 0,
        "channels": [],
    }


def test_long_alias_is_cut_and_bad_point_dropped() -> None:
    out = stats.handle_request(
        _Reader(
            {
                "channels": [
                    {
                        "active": True,
                        "capacity": 10,
                        "local_balance": 4,
                        "remote_balance": 6,
                        "channel_point": "not-a-point",
                        "peer_alias": "x" * 40,
                    }
                ]
            }
        )
    )
    assert out["channels"] == [{"peer_alias": "x" * 32}]
    assert "channel_point" not in out["channels"][0]


def test_lists_at_most_eight_active_channels() -> None:
    rows = []
    for index in range(10):
        rows.append(
            {
                "active": True,
                "capacity": "1",
                "local_balance": "1",
                "remote_balance": "0",
                "channel_point": f"{index:064x}:0",
                "peer_alias": f"p{index}",
            }
        )
    out = stats.handle_request(_Reader({"channels": rows}))
    assert out["num_active"] == 10
    assert len(out["channels"]) == 8


def test_listchannels_failure_is_unavailable() -> None:
    class Boom:
        def list_channels(self) -> dict:
            raise RuntimeError("permission denied: secret path")

    with pytest.raises(stats.LndUnavailable):
        stats.handle_request(Boom())


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise stats.LndUnavailable("hidden")

    monkeypatch.setattr(stats, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden" not in raw


def test_post_is_405() -> None:
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/lightning/ln-channel-stats$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-channel-stats"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    assert "https://agent-bitcoin.net/paid/lightning/ln-channel-stats" in script
    bake = (root / "docs" / "l402-aperture.md").read_text(encoding="utf-8")
    assert "uri:/lnrpc.Lightning/ListChannels" in bake
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_channel_stats.py" in dockerfile
