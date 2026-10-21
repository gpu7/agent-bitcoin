"""Channel reserve check. One ListChannels. Does not pay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_channel_reserve_check as reserve
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-channel-reserve-check"
_PEER = "02" + "aa" * 32
_OTHER = "03" + "bb" * 32
_POINT = "ab" * 32 + ":0"


class _Reader:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def list_channels(self) -> dict:
        self.calls.append("list_channels")
        return self.payload


def _channels() -> dict:
    return {
        "channels": [
            {
                "remote_pubkey": _OTHER,
                "local_balance": 1,
                "remote_balance": 2,
                "local_chan_reserve_sat": 1,
                "remote_chan_reserve_sat": 1,
                "active": False,
            },
            {
                "remote_pubkey": _PEER.upper(),
                "local_balance": 5000,
                "remote_balance": 8000,
                "local_chan_reserve_sat": 600,
                "remote_chan_reserve_sat": 700,
                "active": True,
                "channel_point": _POINT,
                "htlcs": [{"preimage": "secret-preimage"}],
            },
        ]
    }


def _body(amount: int = 1000) -> bytes:
    return json.dumps({"peer_pubkey": _PEER, "amount_sats": amount}).encode()


def test_reserve_headroom_for_the_matching_peer() -> None:
    reader = _Reader(_channels())
    out = reserve.handle_request(_body(), reader)
    dumped = json.dumps(out)
    assert out == {
        "sufficient_local": True,
        "sufficient_remote": True,
        "local_balance": 5000,
        "remote_balance": 8000,
        "local_reserve": 600,
        "remote_reserve": 700,
        "active": True,
    }
    tight = reserve.handle_request(_body(4500), reader)
    assert tight["sufficient_local"] is False
    assert tight["sufficient_remote"] is True
    assert tight["active"] is True
    assert _PEER not in dumped
    assert _POINT not in dumped
    assert "secret-preimage" not in dumped
    assert "preimage" not in dumped
    assert reader.calls == ["list_channels", "list_channels"]


def test_missing_reserve_counts_as_zero() -> None:
    reader = _Reader(
        {
            "channels": [
                {
                    "remote_pubkey": _PEER,
                    "local_balance": 1000,
                    "remote_balance": 1000,
                    "active": False,
                }
            ]
        }
    )
    out = reserve.handle_request(_body(1000), reader)
    assert out["local_reserve"] == 0
    assert out["remote_reserve"] == 0
    assert out["sufficient_local"] is True
    assert out["sufficient_remote"] is True
    assert out["active"] is False


def test_amount_below_floor_does_not_call_list_channels() -> None:
    reader = _Reader(_channels())
    with pytest.raises(reserve.BadAmount):
        reserve.handle_request(_body(50), reader)
    with pytest.raises(reserve.BadAmount):
        reserve.handle_request(
            json.dumps({"peer_pubkey": _PEER, "amount_sats": True}).encode(),
            reader,
        )
    assert reader.calls == []


def test_missing_balance_is_unavailable() -> None:
    reader = _Reader(
        {"channels": [{"remote_pubkey": _PEER, "remote_balance": 1000, "active": True}]}
    )
    with pytest.raises(reserve.LndUnavailable):
        reserve.handle_request(_body(), reader)


def test_no_match_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader({"channels": []})
    with pytest.raises(reserve.ChannelNotFound):
        reserve.handle_request(_body(), reader)
    monkeypatch.setattr(reserve, "_get_reader", lambda _injected=None: reader)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=_body())
    assert status == 404
    assert json.loads(raw) == {"ok": False, "error": "channel_not_found"}
    assert _PEER.encode() not in raw


def test_allowlist_is_list_channels_only() -> None:
    class Raw:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def list_channels(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("list_channels")
            return {}

        def send_payment(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("send_payment")
            return {}

    raw = Raw()
    grpc = reserve._Grpc(raw)
    assert reserve._ALLOWED == frozenset({"list_channels"})
    with pytest.raises(reserve.LndUnavailable):
        grpc._call("send_payment")
    assert raw.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(reserve, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise reserve.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(reserve, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=_body())
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-channel-reserve-check"
    needle = 'pathregexp: "^/paid/lightning/ln-channel-reserve-check$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-channel-reserve-check"' in text
        assert text.index('name: "ln-invoice-amount-check"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_channel_reserve_check.py" in docker
