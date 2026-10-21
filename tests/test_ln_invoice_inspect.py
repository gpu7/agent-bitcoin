"""BOLT11 inspect. No live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_invoice_inspect as inspect
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-invoice-inspect"
_BOLT = "lnbc1inspectsecretvalue"
_DEST = "02" + "cd" * 32
_HASH = "ab" * 32
_HINT = "secrethintnode"


class _Reader:
    def __init__(self, payload: dict | Exception) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def decode_pay_req(self, bolt11: str) -> dict:
        self.calls.append("decode_pay_req")
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _decoded() -> dict:
    return {
        "num_msat": "2000000",
        "expiry": 3600,
        "payment_hash": _HASH.upper(),
        "destination": _DEST.upper(),
        "cltv_expiry": 40,
        "description": "  coffee  ",
        "features": {"9": {"name": "tlv"}, "14": {"name": "payment-addr"}},
        "route_hints": [{"hop_hints": [{"node_id": _HINT}]}],
        "payment_addr": "secretaddr",
    }


def test_decode_returns_public_fields() -> None:
    reader = _Reader(_decoded())
    out = inspect.handle_request(json.dumps({"bolt11": _BOLT}).encode(), reader)
    dumped = json.dumps(out)
    assert out["amount_msat"] == 2_000_000
    assert out["expiry"] == 3600
    assert out["payment_hash"] == _HASH
    assert out["cltv_expiry"] == 40
    assert out["description"] == "coffee"
    assert out["destination"] == f"{_DEST[:8]}…{_DEST[-4:]}"
    assert out["features"] == [9, 14]
    assert _BOLT not in dumped
    assert _DEST not in dumped
    assert _HINT not in dumped
    assert "secretaddr" not in dumped
    assert reader.calls == ["decode_pay_req"]


def test_garbage_invoice_is_400_before_rpc() -> None:
    reader = _Reader(_decoded())
    with pytest.raises(inspect.BadInvoice):
        inspect.handle_request(
            json.dumps({"bolt11": "not-an-invoice"}).encode(), reader
        )
    assert reader.calls == []


def test_lnd_reject_is_bad_invoice() -> None:
    reader = _Reader(RuntimeError("checksum failed"))
    with pytest.raises(inspect.BadInvoice):
        inspect.handle_request(json.dumps({"bolt11": _BOLT}).encode(), reader)


def test_post_origin_200(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader(_decoded())
    monkeypatch.setattr(inspect, "_get_reader", lambda _injected=None: reader)
    status, content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"bolt11": _BOLT}).encode()
    )
    assert status == 200
    assert content_type == "application/json"
    assert json.loads(raw)["payment_hash"] == _HASH
    assert _BOLT.encode() not in raw


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(inspect, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise inspect.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(inspect, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"bolt11": _BOLT}).encode()
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-invoice-inspect"
    needle = 'pathregexp: "^/paid/lightning/ln-invoice-inspect$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-invoice-inspect"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_invoice_inspect.py" in docker
