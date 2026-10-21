"""Payee liquidity hint. Public graph capacity. Not a balance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_payee_liquidity_hint as hint
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-payee-liquidity-hint"
_PUB = "02" + "ab" * 32
_OTHER = "03" + "cd" * 32
_NOTE = "Public graph capacity. Not channel balances."


class _Reader:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or {}
        self.calls: list[tuple] = []

    def get_node_info(self, pub_key: str, include_channels: bool = False) -> dict:
        self.calls.append((pub_key, include_channels))
        return self.payload


def _graph() -> dict:
    return {
        "total_capacity": 500_000,
        "channels": [
            {
                "chan_point": "secretpoint",
                "node1_pub": _PUB,
                "node2_pub": _OTHER,
                "node1_policy": {
                    "fee_base_msat": 1000,
                    "fee_rate_milli_msat": 100,
                    "disabled": False,
                },
                "node2_policy": {
                    "fee_base_msat": 9,
                    "fee_rate_milli_msat": 9,
                    "disabled": False,
                },
            },
            {
                "node1_pub": _OTHER,
                "node2_pub": _PUB,
                "node2_policy": {
                    "fee_base_msat": 3000,
                    "fee_rate_milli_msat": 50,
                    "disabled": False,
                },
            },
            {
                "node1_pub": _PUB,
                "node1_policy": {
                    "fee_base_msat": 1,
                    "fee_rate_milli_msat": 1,
                    "disabled": True,
                },
            },
        ],
    }


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            found.update(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_keys(item))
    return found


def test_hint_reports_capacity_and_fee_range() -> None:
    reader = _Reader(_graph())
    body = json.dumps({"pubkey": _PUB, "amount_sats": 1000}).encode()
    out = hint.handle_request(body, reader)
    dumped = json.dumps(out)
    assert out["hint"] is True
    assert out["total_capacity_sats"] == 500_000
    assert out["capacity_covers_amount"] is True
    assert out["note"] == _NOTE
    assert out["min_fee_base_msat"] == 1000
    assert out["max_fee_base_msat"] == 3000
    assert out["min_fee_rate_milli_msat"] == 50
    assert out["max_fee_rate_milli_msat"] == 100
    assert "local_balance" not in _keys(out)
    assert "remote_balance" not in _keys(out)
    assert "balance" not in _keys(out)
    assert "secretpoint" not in dumped
    assert _PUB not in dumped
    assert _OTHER not in dumped
    assert reader.calls == [(_PUB, True)]


def test_amount_50_is_400_before_rpc() -> None:
    reader = _Reader(_graph())
    body = json.dumps({"pubkey": _PUB, "amount_sats": 50}).encode()
    with pytest.raises(hint.BadAmount):
        hint.handle_request(body, reader)
    assert reader.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(hint, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise hint.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(hint, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE,
        method="POST",
        body=json.dumps({"pubkey": _PUB, "amount_sats": 1000}).encode(),
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-payee-liquidity-hint"
    needle = 'pathregexp: "^/paid/lightning/ln-payee-liquidity-hint$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-payee-liquidity-hint"' in text
        assert text.index('name: "ln-invoice-create"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 500]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_payee_liquidity_hint.py" in docker
