"""Pay check. Decode plus QueryRoutes. Does not pay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_pay_check as pay
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-pay-check"
_BOLT = "lnbc1paycheck"
_DEST = "02" + "ab" * 32
_NOW = 2_000_000_000


class _Reader:
    def __init__(self, decoded: dict | None = None, route: dict | None = None) -> None:
        self.decoded = decoded or {}
        self.route = route or {}
        self.calls: list[tuple] = []

    def decode_pay_req(self, bolt11: str) -> dict:
        self.calls.append(("decode_pay_req", bolt11))
        return self.decoded

    def query_routes(self, dest: str, amount_sats: int) -> dict:
        self.calls.append(("query_routes", dest, amount_sats))
        return self.route


def _invoice(**extra: object) -> dict:
    row = {
        "destination": _DEST,
        "num_satoshis": 1000,
        "timestamp": _NOW,
        "expiry": 3600,
    }
    row.update(extra)
    return row


def _route(fees_msat: int = 2500) -> dict:
    return {"routes": [{"total_fees_msat": fees_msat, "hops": [{}, {}]}]}


def test_fee_under_max_allows() -> None:
    reader = _Reader(_invoice(), _route())
    body = json.dumps({"bolt11": _BOLT, "max_fee_sats": 5}).encode()
    out = pay.handle_request(body, reader, now=_NOW)
    dumped = json.dumps(out)
    assert out["allow"] is True
    assert out["reasons"] == []
    assert out["fee_sats"] == 3
    assert out["hop_count"] == 2
    assert _BOLT not in dumped
    assert reader.calls == [
        ("decode_pay_req", _BOLT),
        ("query_routes", _DEST, 1000),
    ]


def test_fee_above_max_denies_and_returns_fee() -> None:
    reader = _Reader(_invoice(), _route())
    body = json.dumps({"bolt11": _BOLT, "max_fee_sats": 2}).encode()
    out = pay.handle_request(body, reader, now=_NOW)
    assert out["allow"] is False
    assert out["reasons"] == ["fee_above_max"]
    assert out["fee_sats"] == 3
    assert out["hop_count"] == 2


def test_expired_invoice_does_not_query() -> None:
    reader = _Reader(_invoice(timestamp=1, expiry=1))
    body = json.dumps({"bolt11": _BOLT}).encode()
    out = pay.handle_request(body, reader, now=_NOW)
    assert out == {
        "allow": False,
        "reasons": ["expired"],
        "fee_sats": None,
        "hop_count": None,
    }
    assert reader.calls == [("decode_pay_req", _BOLT)]


def test_no_route_is_allow_false(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader(_invoice(), {"routes": []})
    body = json.dumps({"bolt11": _BOLT}).encode()
    out = pay.handle_request(body, reader, now=_NOW)
    assert out["allow"] is False
    assert out["reasons"] == ["no_route"]
    assert out["fee_sats"] is None
    monkeypatch.setattr(pay, "_get_reader", lambda _injected: reader)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=body)
    assert status == 200
    assert json.loads(raw)["reasons"] == ["no_route"]


def test_both_shapes_are_400_before_rpc() -> None:
    reader = _Reader(_invoice(), _route())
    body = json.dumps(
        {"bolt11": _BOLT, "dest_pubkey": _DEST, "amount_sats": 1000}
    ).encode()
    with pytest.raises(pay.BadInput):
        pay.handle_request(body, reader, now=_NOW)
    assert reader.calls == []


def test_allowlist_rejects_get_node_info_and_send_payment() -> None:
    class Raw:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def decode_pay_req(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("decode_pay_req")
            return {}

        def query_routes(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("query_routes")
            return {}

        def get_node_info(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("get_node_info")
            return {}

        def send_payment(self, *_args: object, **_kwargs: object) -> dict:
            self.calls.append("send_payment")
            return {}

    raw = Raw()
    grpc = pay._Grpc(raw)
    assert pay._ALLOWED == frozenset({"decode_pay_req", "query_routes"})
    for name in ("get_node_info", "send_payment"):
        with pytest.raises(pay.LndUnavailable):
            grpc._call(name, _DEST)
    assert raw.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(pay, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise pay.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(pay, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE, method="POST", body=json.dumps({"bolt11": _BOLT}).encode()
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-pay-check"
    needle = 'pathregexp: "^/paid/lightning/ln-pay-check$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-pay-check"' in text
        assert text.index('name: "ln-invoice-create"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_pay_check.py" in docker
