"""Channel policy from listchannels. No live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_channel_policy as policy
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-channel-policy"
_PEER = "02" + "aa" * 32


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
                "remote_pubkey": _PEER,
                "active": True,
                "fee_base_msat": 7,
                "fee_rate_milli_msat": 100,
                "local_constraints": {
                    "min_htlc_msat": 1000,
                    "max_pending_amt_msat": 5_000_000,
                    "csv_delay": 40,
                    "fee_base_msat": 7,
                },
            }
        ]
    }


def test_constraints_omit_fee_fields() -> None:
    reader = _Reader(_channels())
    out = policy.handle_request(b"{}", reader)
    dumped = json.dumps(out)
    assert out == {
        "channels": [
            {
                "remote_pubkey": f"{_PEER[:8]}…{_PEER[-4:]}",
                "active": True,
                "min_htlc_msat": 1000,
                "max_htlc_msat": 5_000_000,
                "time_lock_delta": 40,
            }
        ]
    }
    assert "fee_base_msat" not in dumped
    assert "fee_rate_milli_msat" not in dumped
    assert _PEER not in dumped
    assert reader.calls == ["list_channels"]


def test_invalid_pubkey_does_not_call_list_channels() -> None:
    reader = _Reader(_channels())
    with pytest.raises(policy.BadPubkey):
        policy.handle_request(json.dumps({"peer_pubkey": "zz"}).encode(), reader)
    assert reader.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(policy, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise policy.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(policy, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-channel-policy"
    needle = 'pathregexp: "^/paid/lightning/ln-channel-policy$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-channel-policy"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    assert "ln_channel_policy.py" in (root / "l402" / "Dockerfile.origin").read_text()
