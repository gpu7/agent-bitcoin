"""Route options. Decode plus one QueryRoutes. Does not pay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_route_options as routes
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-route-options"
_DEST = "02" + "ab" * 32
_BOLT = "lnbc1routeopts"
_CHAN = "cd" * 16


class _Reader:
    def __init__(self, decoded: dict | None = None, route: dict | None = None) -> None:
        self.decoded = decoded or {}
        self.route = route if route is not None else {"routes": []}
        self.calls: list[tuple] = []

    def decode_pay_req(self, bolt11: str) -> dict:
        self.calls.append(("decode_pay_req", bolt11))
        return self.decoded

    def query_routes(self, *args: object, **kwargs: object) -> dict:
        self.calls.append(("query_routes", args, kwargs))
        return self.route


def _two_routes() -> dict:
    return {
        "routes": [
            {
                "total_fees_msat": 1500,
                "hops": [{"pub_key": _DEST, "chan_id": _CHAN}, {}],
                "success_prob": 0.5,
            },
            {
                "total_fees_msat": 2500,
                "hops": [{}],
                "success_prob": True,
            },
        ]
    }


def test_max_routes_slices_and_keeps_fee_fields() -> None:
    reader = _Reader(route=_two_routes())
    body = json.dumps(
        {"dest_pubkey": _DEST, "amount_sats": 1000, "max_routes": 1}
    ).encode()
    one = routes.handle_request(body, reader)
    assert one == {
        "routes": [
            {"total_fees_msat": 1500, "hop_count": 2, "success_prob": 0.5},
        ]
    }
    default_body = json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode()
    both = routes.handle_request(default_body, reader)
    assert len(both["routes"]) == 2
    assert both["routes"][0]["total_fees_msat"] == 1500
    assert both["routes"][0]["hop_count"] == 2
    assert both["routes"][0]["success_prob"] == 0.5
    assert both["routes"][1] == {"total_fees_msat": 2500, "hop_count": 1}
    assert "success_prob" not in both["routes"][1]
    dumped = json.dumps(both)
    assert _DEST not in dumped
    assert _CHAN not in dumped
    assert reader.calls == [
        ("query_routes", (_DEST, 1000), {}),
        ("query_routes", (_DEST, 1000), {}),
    ]


def test_bolt11_queries_once_when_amount_matches() -> None:
    reader = _Reader(
        {"destination": _DEST, "num_satoshis": 1000},
        {"routes": [{"total_fees_msat": 100, "hops": [{}]}]},
    )
    body = json.dumps({"bolt11": _BOLT, "amount_sats": 1000}).encode()
    out = routes.handle_request(body, reader)
    assert out["routes"][0]["hop_count"] == 1
    assert _BOLT not in json.dumps(out)
    assert reader.calls == [
        ("decode_pay_req", _BOLT),
        ("query_routes", (_DEST, 1000), {}),
    ]


def test_amount_less_invoice_uses_supplied_amount() -> None:
    reader = _Reader({"destination": _DEST}, _two_routes())
    body = json.dumps({"bolt11": "lnbcrt1open", "amount_sats": 1000}).encode()
    routes.handle_request(body, reader)
    assert reader.calls[-1] == ("query_routes", (_DEST, 1000), {})


def test_prefix_walk_is_longest_first() -> None:
    assert routes._network("lnbcrt1abc") == "regtest"
    assert routes._network("lntbs1abc") == "signet"
    assert routes._network("lnbc1abc") == "bitcoin"
    assert routes._network("lntb1abc") == "testnet"
    assert routes._network("lnfoo1abc") is None


def test_both_shapes_are_400_before_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader(route=_two_routes())
    body = json.dumps(
        {"bolt11": _BOLT, "dest_pubkey": _DEST, "amount_sats": 1000}
    ).encode()
    with pytest.raises(routes.BadInput):
        routes.handle_request(body, reader)
    with pytest.raises(routes.BadInput):
        routes.handle_request(
            json.dumps({"dest_pubkey": "zz", "amount_sats": 1000}).encode(),
            reader,
        )
    with pytest.raises(routes.BadInput):
        routes.handle_request(
            json.dumps({"dest_pubkey": _DEST, "amount_sats": 50}).encode(),
            reader,
        )
    with pytest.raises(routes.BadInput):
        routes.handle_request(
            json.dumps(
                {"dest_pubkey": _DEST, "amount_sats": 1000, "max_routes": True}
            ).encode(),
            reader,
        )
    assert reader.calls == []
    monkeypatch.setattr(routes, "_get_reader", lambda _injected=None: reader)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=body)
    assert status == 400
    assert json.loads(raw) == {"ok": False, "error": "bad_input"}


def test_bad_invoice_does_not_query() -> None:
    reader = _Reader()

    def reject(bolt11: str) -> dict:
        reader.calls.append(("decode_pay_req", bolt11))
        raise RuntimeError("checksum failed")

    reader.decode_pay_req = reject  # type: ignore[method-assign]
    with pytest.raises(routes.BadInvoice):
        routes.handle_request(
            json.dumps({"bolt11": "lnfoo1nope", "amount_sats": 1000}).encode(),
            reader,
        )
    with pytest.raises(routes.BadInvoice):
        routes.handle_request(
            json.dumps({"bolt11": _BOLT, "amount_sats": 1000}).encode(), reader
        )
    assert reader.calls == [("decode_pay_req", _BOLT)]


def test_fixed_amount_mismatch_does_not_query() -> None:
    reader = _Reader({"destination": _DEST, "num_satoshis": 1000})
    body = json.dumps({"bolt11": _BOLT, "amount_sats": 2000}).encode()
    with pytest.raises(routes.BadInput):
        routes.handle_request(body, reader)
    assert reader.calls == [("decode_pay_req", _BOLT)]


def test_empty_routes_are_200(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader(route={"routes": []})
    body = json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode()
    assert routes.handle_request(body, reader) == {"routes": []}
    monkeypatch.setattr(routes, "_get_reader", lambda _injected=None: reader)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=body)
    assert status == 200
    assert json.loads(raw) == {"routes": []}


def test_unreadable_fee_is_unavailable() -> None:
    reader = _Reader(route={"routes": [{"hops": [{}]}]})
    body = json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode()
    with pytest.raises(routes.LndUnavailable):
        routes.handle_request(body, reader)


def test_allowlist_rejects_send_payment() -> None:
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
    grpc = routes._Grpc(raw)
    assert routes._ALLOWED == frozenset({"decode_pay_req", "query_routes"})
    for name in ("get_node_info", "send_payment"):
        with pytest.raises(routes.LndUnavailable):
            grpc._call(name, _DEST)
    assert raw.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(routes, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise routes.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(routes, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE,
        method="POST",
        body=json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode(),
    )
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-route-options"
    needle = 'pathregexp: "^/paid/lightning/ln-route-options$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-route-options"' in text
        assert text.index('name: "ln-payee-liquidity-hint"') < text.index(needle)
        assert text.index(needle) < text.index('name: "ln-invoice-amount-check"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_route_options.py" in docker
