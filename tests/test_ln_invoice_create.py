"""Invoice create. No payment and no live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_invoice_create as create
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-invoice-create"
_HASH = "ef" * 32
_REQUEST = "lnbc1000n1ptestcreate"
_PREIMAGE = "12" * 32


class _Reader:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload
        self.calls: list[tuple] = []

    def add_invoice(self, amount_sats: int, memo: str) -> dict:
        self.calls.append(("add_invoice", amount_sats, memo))
        assert self.payload is not None
        return self.payload


def _created() -> dict:
    return {
        "payment_request": _REQUEST,
        "payment_hash": _HASH.upper(),
        "expiry": 3600,
        "r_preimage": _PREIMAGE,
        "payment_addr": "secretaddr",
    }


def test_amount_1000_returns_invoice() -> None:
    reader = _Reader(_created())
    body = json.dumps({"amount_sats": 1000, "description": "agent invoice"}).encode()
    out = create.handle_request(body, reader)
    dumped = json.dumps(out)
    assert out == {
        "payment_request": _REQUEST,
        "payment_hash": _HASH,
        "expiry": 3600,
    }
    assert _PREIMAGE not in dumped
    assert "secretaddr" not in dumped
    assert reader.calls == [("add_invoice", 1000, "agent invoice")]


def test_amount_50_is_400_before_rpc() -> None:
    reader = _Reader(_created())
    with pytest.raises(create.BadAmount):
        create.handle_request(json.dumps({"amount_sats": 50}).encode(), reader)
    assert reader.calls == []


def test_allowlist_rejects_send_payment() -> None:
    class Raw:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def add_invoice(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("add_invoice")
            return {}

        def send_payment(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("send_payment")
            return {}

    raw = Raw()
    grpc = create._Grpc(raw)
    assert "send_payment" not in create._ALLOWED
    with pytest.raises(create.LndUnavailable):
        grpc._call("send_payment", _REQUEST)
    assert raw.calls == []


def test_post_origin_200(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader(_created())
    monkeypatch.setattr(create, "_get_reader", lambda _injected=None: reader)
    status, _content_type, raw = dispatch(
        _ROUTE,
        method="POST",
        body=json.dumps({"amount_sats": 1000}).encode(),
    )
    assert status == 200
    assert json.loads(raw)["payment_request"] == _REQUEST


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(create, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise create.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(create, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"amount_sats": 1000}).encode()
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


_READ_URIS = (
    "uri:/lnrpc.Lightning/QueryRoutes",
    "uri:/lnrpc.Lightning/DecodePayReq",
    "uri:/lnrpc.Lightning/ListChannels",
    "uri:/lnrpc.Lightning/GetInfo",
    "uri:/lnrpc.Lightning/GetNodeInfo",
    "uri:/lnrpc.Lightning/ListPeers",
    "uri:/lnrpc.Lightning/LookupInvoice",
)
_WRITE_NAMES = (
    "AddInvoice",
    "SendPayment",
    "SettleInvoice",
    "OpenChannel",
    "BakeMacaroon",
)


def test_origin_macaroon_rejects_invoice_creation() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "l402-aperture.md").read_text(encoding="utf-8")
    start = text.index("bakemacaroon")
    block = text[start : text.index("```", start)]
    uris = [
        line.strip().rstrip("\\").strip()
        for line in block.splitlines()
        if "uri:/" in line
    ]
    assert uris == list(_READ_URIS)
    for name in _WRITE_NAMES:
        assert name not in block


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-invoice-create"
    needle = 'pathregexp: "^/paid/lightning/ln-invoice-create$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-invoice-create"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    assert "ln_invoice_create.py" in (root / "l402" / "Dockerfile.origin").read_text()
