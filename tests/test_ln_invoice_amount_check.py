"""Invoice amount check. DecodePayReq only. Does not query a route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_invoice_amount_check as amt
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-invoice-amount-check"
_BOLT = "lnbc1amountcheck"


class _Reader:
    def __init__(self, decoded: dict | None = None) -> None:
        self.decoded = decoded or {}
        self.calls: list[str] = []

    def decode_pay_req(self, bolt11: str) -> dict:
        self.calls.append(bolt11)
        return self.decoded


def test_zero_amount_requires_supplied_amount() -> None:
    reader = _Reader({})
    body = json.dumps({"bolt11": _BOLT}).encode()
    out = amt.handle_request(body, reader)
    dumped = json.dumps(out)
    assert out == {
        "amount_less": True,
        "amount_msat": 0,
        "supplied_amount_sats": None,
        "within_bounds": False,
        "reason": "amount_required",
    }
    assert _BOLT not in dumped
    assert reader.calls == [_BOLT]


def test_supplied_amount_on_open_invoice_is_in_bounds() -> None:
    reader = _Reader({})
    body = json.dumps({"bolt11": _BOLT, "amount_sats": 1000}).encode()
    out = amt.handle_request(body, reader)
    assert out["amount_less"] is True
    assert out["amount_msat"] == 0
    assert out["supplied_amount_sats"] == 1000
    assert out["within_bounds"] is True
    assert out["reason"] == ""


def test_fixed_amount_match_and_mismatch() -> None:
    reader = _Reader({"num_satoshis": 1000})
    match = amt.handle_request(
        json.dumps({"bolt11": _BOLT, "amount_sats": 1000}).encode(),
        reader,
    )
    assert match["amount_less"] is False
    assert match["amount_msat"] == 1_000_000
    assert match["within_bounds"] is True
    assert match["reason"] == ""
    mismatch = amt.handle_request(
        json.dumps({"bolt11": _BOLT, "amount_sats": 2000}).encode(),
        reader,
    )
    assert mismatch["amount_less"] is False
    assert mismatch["within_bounds"] is False
    assert mismatch["reason"] == "amount_mismatch"
    assert mismatch["supplied_amount_sats"] == 2000
    assert _BOLT not in json.dumps(mismatch)


def test_floor_and_ceiling() -> None:
    low = amt.handle_request(
        json.dumps({"bolt11": _BOLT, "amount_sats": 50}).encode(),
        _Reader({}),
    )
    assert low["within_bounds"] is False
    assert low["reason"] == "below_floor"
    high = amt.handle_request(
        json.dumps({"bolt11": _BOLT}).encode(),
        _Reader({"num_satoshis": 60_000}),
    )
    assert high["amount_less"] is False
    assert high["within_bounds"] is False
    assert high["reason"] == "above_max"
    assert high["supplied_amount_sats"] is None


def test_bad_input_skips_decode() -> None:
    reader = _Reader({"num_satoshis": 1000})
    with pytest.raises(amt.BadInput):
        amt.handle_request(
            json.dumps({"bolt11": _BOLT, "amount_sats": True}).encode(), reader
        )
    with pytest.raises(amt.BadInput):
        amt.handle_request(
            json.dumps({"bolt11": _BOLT, "network": "bitcoin"}).encode(), reader
        )
    with pytest.raises(amt.BadInput):
        amt.handle_request(
            json.dumps({"bolt11": "ln" + ("a" * 4095)}).encode(),
            reader,
        )
    assert reader.calls == []


def test_decode_rejection_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader()

    def reject(bolt11: str) -> dict:
        reader.calls.append(bolt11)
        raise RuntimeError("checksum failed")

    reader.decode_pay_req = reject  # type: ignore[method-assign]
    body = json.dumps({"bolt11": _BOLT}).encode()
    with pytest.raises(amt.BadInvoice):
        amt.handle_request(body, reader)
    monkeypatch.setattr(amt, "_get_reader", lambda _injected=None: reader)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=body)
    assert status == 400
    assert json.loads(raw) == {"ok": False, "error": "bad_invoice"}
    assert b"checksum" not in raw


def test_query_routes_is_not_allowed() -> None:
    class Raw:
        def decode_pay_req(self, *_args: object, **_kwargs: object) -> dict:
            return {}

        def query_routes(self, *_args: object, **_kwargs: object) -> dict:
            raise AssertionError("rpc")

        def send_payment(self, *_args: object, **_kwargs: object) -> dict:
            raise AssertionError("rpc")

    grpc = amt._Grpc(Raw())
    assert amt._ALLOWED == frozenset({"decode_pay_req"})
    assert "query_routes" not in amt._ALLOWED
    for name in ("query_routes", "send_payment"):
        with pytest.raises(amt.LndUnavailable):
            grpc._call(name, _BOLT)


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(amt, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise amt.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(amt, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"bolt11": _BOLT}).encode()
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-invoice-amount-check"
    needle = 'pathregexp: "^/paid/lightning/ln-invoice-amount-check$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-invoice-amount-check"' in text
        assert text.index('name: "ln-route-options"') < text.index(needle)
        assert text.index(needle) < text.index('name: "ln-channel-reserve-check"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_invoice_amount_check.py" in docker
