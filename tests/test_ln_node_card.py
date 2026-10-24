"""Node card. One GetNodeInfo. The full pubkey stays out of the response."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_node_card as card
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-node-card"
_PUB = "02" + "ab" * 32


class _Reader:
    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload or {}
        self.error = error
        self.calls: list[tuple] = []

    def get_node_info(self, pub_key: str, include_channels: bool = False) -> dict:
        self.calls.append((pub_key, include_channels))
        if self.error is not None:
            raise self.error
        return self.payload


def _graph() -> dict:
    return {
        "node": {
            "alias": "Cafe Node",
            "pub_key": _PUB,
            "last_update": 1_700_000_000,
            "addresses": [
                {"network": "tcp", "addr": "198.51.100.10:9735"},
                {"network": "tcp", "addr": "[2001:db8::1]:9735"},
                {"network": "tcp", "addr": "node.example.com:9735"},
                {"network": "tcp", "addr": "second.example.com"},
                {"network": "tcp", "addr": "third.example.com:9735"},
            ],
        },
        "num_channels": 4,
        "total_capacity": 2_500_000,
    }


def test_card_shortens_addresses_and_hides_pubkey() -> None:
    reader = _Reader(_graph())
    out = card.handle_request(json.dumps({"pubkey": _PUB}).encode(), reader)
    dumped = json.dumps(out)
    assert out["alias"] == "Cafe Node"
    assert out["num_channels"] == 4
    assert out["total_capacity_sats"] == 2_500_000
    assert out["last_update"] == 1_700_000_000
    assert out["addresses"] == [
        "198.51.100.10",
        "2001:db8::1",
        "node.example.com",
        "second.example.com",
    ]
    assert out["truncated"] is True
    assert _PUB not in dumped
    assert "9735" not in dumped
    assert reader.calls == [(_PUB, False)]


def test_not_found_code_is_node_not_found() -> None:
    class _Status:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Missing(Exception):
        def code(self) -> _Status:
            return _Status("NOT_FOUND")

    class _Denied(Exception):
        def code(self) -> _Status:
            return _Status("PERMISSION_DENIED")

    with pytest.raises(card.NodeNotFound):
        card._classify(_Missing())
    with pytest.raises(card.LndUnavailable):
        card._classify(_Denied())


def test_unknown_node_is_404() -> None:
    reader = _Reader(error=RuntimeError("unable to find node"))
    with pytest.raises(card.NodeNotFound):
        card.handle_request(json.dumps({"pubkey": _PUB}).encode(), reader)
    assert reader.calls == [(_PUB, False)]


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(card, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unknown_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise card.NodeNotFound("hidden node text")

    monkeypatch.setattr(card, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"pubkey": _PUB}).encode()
    )
    assert status == 404
    assert json.loads(raw) == {"ok": False, "error": "node_not_found"}
    assert b"hidden node text" not in raw


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise card.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(card, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"pubkey": _PUB}).encode()
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-node-card"
    needle = 'pathregexp: "^/paid/lightning/ln-node-card$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-node-card"' in text
        assert text.index('name: "ln-invoice-create"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_node_card.py" in docker
