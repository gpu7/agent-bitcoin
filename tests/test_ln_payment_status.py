"""Invoice payment status. No live LND and no list_payments scan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_payment_status as status_mod
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-payment-status"
_HASH = "ab" * 32
_PREIMAGE = "cd" * 32
_INVOICE = "lnbc1statussecretinvoice"


class _Reader:
    def __init__(self, payload: dict | Exception) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def lookup_invoice(self, payment_hash: str) -> dict:
        self.calls.append("lookup_invoice")
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _settled() -> dict:
    return {
        "state": "SETTLED",
        "value_msat": "1000000",
        "creation_date": "1710000000",
        "r_preimage": _PREIMAGE,
        "payment_request": _INVOICE,
        "memo": "secret memo",
        "payment_addr": "secretaddr",
    }


def test_settled_invoice_is_succeeded() -> None:
    reader = _Reader(_settled())
    out = status_mod.handle_request(
        json.dumps({"payment_hash": _HASH}).encode(), reader
    )
    dumped = json.dumps(out)
    assert out == {
        "status": "succeeded",
        "value_msat": 1_000_000,
        "creation_date": 1_710_000_000,
    }
    assert _PREIMAGE not in dumped
    assert _INVOICE not in dumped
    assert "secret memo" not in dumped
    assert reader.calls == ["lookup_invoice"]


def test_lookup_not_found_code_is_payment_not_found() -> None:
    class _Status:
        def __init__(self, name: str) -> None:
            self.name = name

    class _Missing(Exception):
        def code(self) -> _Status:
            return _Status("NOT_FOUND")

    class _Denied(Exception):
        def code(self) -> _Status:
            return _Status("PERMISSION_DENIED")

    with pytest.raises(status_mod.PaymentNotFound):
        status_mod._classify_lookup(_Missing())
    with pytest.raises(status_mod.LndUnavailable):
        status_mod._classify_lookup(_Denied())


def test_omitted_open_state_is_pending() -> None:
    reader = _Reader(
        {
            "value_msat": "1000000",
            "creation_date": "1710000000",
            "payment_request": _INVOICE,
        }
    )
    out = status_mod.handle_request(
        json.dumps({"payment_hash": _HASH}).encode(), reader
    )
    assert out["status"] == "pending"
    assert _INVOICE not in json.dumps(out)


def test_unknown_hash_is_not_found() -> None:
    reader = _Reader(RuntimeError("unable to locate invoice"))
    with pytest.raises(status_mod.PaymentNotFound):
        status_mod.handle_request(json.dumps({"payment_hash": _HASH}).encode(), reader)


def test_unknown_hash_origin_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise status_mod.PaymentNotFound("hidden invoice text")

    monkeypatch.setattr(status_mod, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"payment_hash": _HASH}).encode()
    )
    assert status == 404
    assert json.loads(raw) == {"ok": False, "error": "payment_not_found"}
    assert b"hidden invoice text" not in raw


def test_list_payments_is_not_on_the_allowlist() -> None:
    class Raw:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def lookup_invoice(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("lookup_invoice")
            return {}

        def list_payments(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("list_payments")
            return {}

    raw = Raw()
    grpc = status_mod._Grpc(raw)
    assert "list_payments" not in status_mod._ALLOWED
    with pytest.raises(status_mod.LndUnavailable):
        grpc._call("list_payments")
    assert raw.calls == []


def test_bad_json_is_bad_input() -> None:
    with pytest.raises(status_mod.BadInput):
        status_mod.handle_request(b"{", None)


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(status_mod, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise status_mod.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(status_mod, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"payment_hash": _HASH}).encode()
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-payment-status"
    needle = 'pathregexp: "^/paid/lightning/ln-payment-status$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-payment-status"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    assert "ln_payment_status.py" in (root / "l402" / "Dockerfile.origin").read_text()
