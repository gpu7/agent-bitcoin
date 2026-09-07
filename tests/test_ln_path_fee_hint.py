"""ABT-L402-011 — ln-path-fee-hint POST, XOR, mocked QueryRoutes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from l402 import ln_path_fee_hint as hint
from l402.origin import dispatch

_FIXED_NOW = datetime(2026, 9, 7, 19, 20, 0, tzinfo=timezone.utc)
_DEST = "02" + ("ab" * 32)
_BOLT11 = "lnbc1testinvoice"


@pytest.fixture(autouse=True)
def _reset():
    hint.reset_cache()
    yield
    hint.reset_cache()


class SpyRouter:
    def __init__(
        self,
        *,
        decoded: dict | None = None,
        routes: dict | None = None,
        decode_exc: Exception | None = None,
        query_exc: Exception | None = None,
    ) -> None:
        self.calls: list[tuple] = []
        self._decoded = decoded or {
            "destination": _DEST,
            "num_satoshis": "1000",
            "payment_hash": "aa" * 32,
        }
        self._routes = (
            routes
            if routes is not None
            else {
                "routes": [
                    {"hops": [{}, {}, {}], "total_fees_msat": "12000"},
                ],
                "success_prob": 0.82,
            }
        )
        self._decode_exc = decode_exc
        self._query_exc = query_exc

    def decode_pay_req(self, bolt11: str) -> dict:
        self.calls.append(("decode_pay_req", bolt11[:12]))
        if self._decode_exc:
            raise self._decode_exc
        return dict(self._decoded)

    def query_routes(self, dest: str, amount_sats: int) -> dict:
        self.calls.append(("query_routes", dest, amount_sats))
        if self._query_exc:
            raise self._query_exc
        return dict(self._routes)

    def send_payment(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("SendPayment must not be called")


def _body(**kwargs) -> bytes:
    return json.dumps(kwargs).encode("utf-8")


def test_dest_form_digest() -> None:
    router = SpyRouter()
    out = hint.handle_request(
        _body(dest_pubkey=_DEST, amount_sats=1000),
        router=router,
        now=_FIXED_NOW,
        ttl_s=15,
        monotonic=lambda: 0.0,
    )
    assert out["ok"] is True
    assert out["service"] == "ln-path-fee-hint"
    assert out["source"] == "aws_agent_lnd"
    assert out["amount_sats"] == 1000
    assert out["fee_sats"] == 12
    assert out["total_sats"] == 1012
    assert out["hop_count"] == 3
    assert out["success_hint"] == 0.82
    assert out["ttl_s"] == 15
    assert "bolt11" not in out
    assert router.calls == [("query_routes", _DEST, 1000)]


def test_bolt11_uses_invoice_amount() -> None:
    router = SpyRouter()
    out = hint.handle_request(
        _body(bolt11=_BOLT11),
        router=router,
        now=_FIXED_NOW,
        monotonic=lambda: 0.0,
    )
    assert out["amount_sats"] == 1000
    assert out["fee_sats"] == 12
    assert ("decode_pay_req", "lnbc1testinv") in router.calls
    assert ("query_routes", _DEST, 1000) in router.calls


def test_xor_both_or_neither() -> None:
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body())
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body(bolt11=_BOLT11, dest_pubkey=_DEST, amount_sats=1000))
    with pytest.raises(hint.BadInput):
        hint.parse_body(b"")
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body(dest_pubkey=_DEST))


def test_amount_bounds() -> None:
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body(dest_pubkey=_DEST, amount_sats=99))
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body(dest_pubkey=_DEST, amount_sats=50001))
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body(dest_pubkey=_DEST, amount_sats=1000.5))
    with pytest.raises(hint.BadInput):
        hint.parse_body(_body(dest_pubkey="00" + ("ab" * 32), amount_sats=1000))


def test_zero_amount_invoice_requires_amount() -> None:
    router = SpyRouter(decoded={"destination": _DEST, "num_satoshis": "0"})
    with pytest.raises(hint.BadInput):
        hint.handle_request(_body(bolt11=_BOLT11), router=router)
    out = hint.handle_request(
        _body(bolt11=_BOLT11, amount_sats=1000),
        router=router,
        now=_FIXED_NOW,
        monotonic=lambda: 0.0,
    )
    assert out["amount_sats"] == 1000


def test_amount_mismatch_invoice() -> None:
    router = SpyRouter()
    with pytest.raises(hint.BadInput):
        hint.handle_request(
            _body(bolt11=_BOLT11, amount_sats=2000),
            router=router,
        )


def test_no_route_raises() -> None:
    router = SpyRouter(query_exc=hint.NoRoute("no_route"))
    with pytest.raises(hint.NoRoute):
        hint.handle_request(
            _body(dest_pubkey=_DEST, amount_sats=1000),
            router=router,
            monotonic=lambda: 0.0,
        )


def test_origin_mock_route_200(monkeypatch) -> None:
    payload = hint.digest_route(
        {
            "routes": [{"hops": [{}, {}, {}], "total_fees_msat": "12000"}],
            "success_prob": 0.82,
        },
        amount_sats=1000,
        now=_FIXED_NOW,
    )
    monkeypatch.setattr(hint, "handle_request", lambda *_a, **_k: payload)
    status, ctype, body = dispatch(
        "/paid/finance/ln-path-fee-hint",
        method="POST",
        body=_body(dest_pubkey=_DEST, amount_sats=1000),
    )
    assert status == 200
    assert ctype == "application/json"
    data = json.loads(body)
    assert data["fee_sats"] == 12
    assert data["hop_count"] == 3
    assert "bolt11" not in data


def test_origin_no_route_404(monkeypatch) -> None:
    def boom(body, **_k):
        raise hint.NoRoute("no_route")

    monkeypatch.setattr(hint, "handle_request", boom)
    status, _ctype, body = dispatch(
        "/paid/finance/ln-path-fee-hint",
        method="POST",
        body=_body(dest_pubkey=_DEST, amount_sats=1000),
    )
    assert status == 404
    assert json.loads(body) == {"ok": False, "error": "no_route"}


def test_origin_lnd_down_503(monkeypatch) -> None:
    def boom(body, **_k):
        raise hint.LndUnavailable("down")

    monkeypatch.setattr(hint, "handle_request", boom)
    status, _ctype, body = dispatch(
        "/paid/finance/ln-path-fee-hint",
        method="POST",
        body=_body(dest_pubkey=_DEST, amount_sats=1000),
    )
    assert status == 503
    assert json.loads(body) == {"ok": False, "error": "lnd_unavailable"}


def test_origin_bad_input_400() -> None:
    status, _ctype, body = dispatch(
        "/paid/finance/ln-path-fee-hint",
        method="POST",
        body=_body(),
    )
    assert status == 400
    assert json.loads(body) == {"ok": False, "error": "bad_input"}


def test_get_405() -> None:
    status, _ctype, body = dispatch("/paid/finance/ln-path-fee-hint", method="GET")
    assert status == 405
    assert json.loads(body) == {"ok": False, "error": "method_not_allowed"}


def test_send_payment_never_called() -> None:
    router = SpyRouter()
    hint.handle_request(
        _body(dest_pubkey=_DEST, amount_sats=1000),
        router=router,
        now=_FIXED_NOW,
        monotonic=lambda: 0.0,
    )
    assert all(c[0] != "send_payment" for c in router.calls)
    with pytest.raises(AssertionError, match="SendPayment"):
        router.send_payment("lnbc1")


def test_missing_macaroon_503(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LND_GRPC_HOST", "lnd")
    monkeypatch.setenv("LND_TLS_CERT_PATH", str(tmp_path / "missing.cert"))
    monkeypatch.setenv("LND_READONLY_MACAROON_PATH", str(tmp_path / "missing.macaroon"))
    with pytest.raises(hint.LndUnavailable):
        hint.connect_router()
    status, _ctype, body = dispatch(
        "/paid/finance/ln-path-fee-hint",
        method="POST",
        body=_body(dest_pubkey=_DEST, amount_sats=1000),
    )
    assert status == 503
    assert json.loads(body)["error"] == "lnd_unavailable"


def test_cache_hit_does_not_requery() -> None:
    router = SpyRouter()
    a = hint.handle_request(
        _body(dest_pubkey=_DEST, amount_sats=1000),
        router=router,
        now=_FIXED_NOW,
        ttl_s=15,
        monotonic=lambda: 0.0,
    )
    b = hint.handle_request(
        _body(dest_pubkey=_DEST, amount_sats=1000),
        router=router,
        now=_FIXED_NOW,
        ttl_s=15,
        monotonic=lambda: 0.0,
    )
    assert a == b
    assert len([c for c in router.calls if c[0] == "query_routes"]) == 1
