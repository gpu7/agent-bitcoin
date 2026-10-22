"""Channel liquidity. No live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_channel_liquidity as liq
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-channel-liquidity"
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
                "remote_pubkey": _PEER.upper(),
                "capacity": 100_000,
                "local_balance": 40_000,
                "remote_balance": 60_000,
                "active": True,
                "channel_point": _POINT,
            },
            {
                "remote_pubkey": _OTHER,
                "capacity": 50,
                "local_balance": 1,
                "remote_balance": 2,
                "active": False,
                "channel_point": "cd" * 32 + ":1",
            },
        ]
    }


def test_filter_returns_one_short_row() -> None:
    reader = _Reader(_channels())
    body = json.dumps({"peer_pubkey": _PEER}).encode()
    out = liq.handle_request(body, reader)
    dumped = json.dumps(out)
    assert out == {
        "channels": [
            {
                "remote_pubkey": f"{_PEER[:8]}…{_PEER[-4:]}",
                "capacity": 100_000,
                "local_balance": 40_000,
                "remote_balance": 60_000,
                "active": True,
            }
        ]
    }
    assert _PEER not in dumped
    assert _POINT not in dumped
    assert reader.calls == ["list_channels"]


def test_omitted_active_is_false() -> None:
    reader = _Reader(
        {
            "channels": [
                {
                    "remote_pubkey": _PEER,
                    "capacity": 10,
                    "local_balance": 4,
                    "remote_balance": 6,
                }
            ]
        }
    )
    out = liq.handle_request(b"{}", reader)
    assert out["channels"][0]["active"] is False


def test_invalid_pubkey_does_not_call_list_channels() -> None:
    reader = _Reader(_channels())
    with pytest.raises(liq.BadPubkey):
        liq.handle_request(json.dumps({"peer_pubkey": "zz"}).encode(), reader)
    assert reader.calls == []


def test_post_origin_200(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader(_channels())
    monkeypatch.setattr(liq, "_get_reader", lambda _injected=None: reader)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"peer_pubkey": _PEER}).encode()
    )
    assert status == 200
    assert json.loads(raw)["channels"][0]["capacity"] == 100_000


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(liq, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise liq.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(liq, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-channel-liquidity"
    needle = 'pathregexp: "^/paid/lightning/ln-channel-liquidity$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-channel-liquidity"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    assert (
        "ln_channel_liquidity.py" in (root / "l402" / "Dockerfile.origin").read_text()
    )
