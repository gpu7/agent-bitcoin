"""Peer status. No live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_peer_status as peers
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-peer-status"
_PEER = "02" + "11" * 32
_ADDRESS = "203.0.113.8:9735"


class _Reader:
    def __init__(self, peer_payload: dict, channel_payload: dict) -> None:
        self.peer_payload = peer_payload
        self.channel_payload = channel_payload
        self.calls: list[str] = []

    def list_peers(self) -> dict:
        self.calls.append("list_peers")
        return self.peer_payload

    def list_channels(self) -> dict:
        self.calls.append("list_channels")
        return self.channel_payload


def _payloads() -> tuple[dict, dict]:
    peers_raw = {
        "peers": [
            {
                "pub_key": _PEER.upper(),
                "address": _ADDRESS,
                "bytes_sent": 999001,
                "sat_sent": 888002,
                "ping_time": 2_500_000_000,
            }
        ]
    }
    channels = {
        "channels": [
            {"remote_pubkey": _PEER, "active": True},
        ]
    }
    return peers_raw, channels


def test_connected_peer_converts_ping() -> None:
    reader = _Reader(*_payloads())
    out = peers.handle_request(b"{}", reader)
    dumped = json.dumps(out)
    assert out == {
        "peers": [
            {
                "remote_pubkey": f"{_PEER[:8]}…{_PEER[-4:]}",
                "connected": True,
                "num_channels": 1,
                "active_channels": 1,
                "last_ping_ms": 2500,
            }
        ]
    }
    assert _ADDRESS not in dumped
    assert "888002" not in dumped
    assert _PEER not in dumped
    assert reader.calls == ["list_peers", "list_channels"]


def test_omitted_active_is_not_counted_active() -> None:
    peers_raw, channels = _payloads()
    del channels["channels"][0]["active"]
    out = peers.handle_request(b"{}", _Reader(peers_raw, channels))
    assert out["peers"][0]["num_channels"] == 1
    assert out["peers"][0]["active_channels"] == 0


def test_list_channels_not_called_when_list_peers_raises() -> None:
    class Boom:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def list_peers(self) -> dict:
            self.calls.append("list_peers")
            raise RuntimeError("secret down")

        def list_channels(self) -> dict:
            self.calls.append("list_channels")
            return {"channels": []}

    reader = Boom()
    with pytest.raises(peers.LndUnavailable) as caught:
        peers.handle_request(b"{}", reader)
    assert reader.calls == ["list_peers"]
    assert "secret down" not in str(caught.value)


def test_invalid_pubkey_does_not_call_rpc() -> None:
    reader = _Reader(*_payloads())
    with pytest.raises(peers.BadPubkey):
        peers.handle_request(json.dumps({"peer_pubkey": "nope"}).encode(), reader)
    assert reader.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(peers, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise peers.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(peers, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-peer-status"
    needle = 'pathregexp: "^/paid/lightning/ln-peer-status$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-peer-status"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    assert "ln_peer_status.py" in (root / "l402" / "Dockerfile.origin").read_text()
