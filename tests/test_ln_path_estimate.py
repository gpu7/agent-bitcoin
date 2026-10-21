"""Path estimate. No live LND and no payment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_path_estimate as estimate
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-path-estimate"
_DEST = "02" + "cd" * 32
_HOP = "03" + "ef" * 32
_BOLT = "lnbc1pathestimatesecret"
_CHAN = "999888777666"


class _Reader:
    def __init__(
        self, payload: dict | None = None, query_exc: Exception | None = None
    ) -> None:
        self.payload = payload or {}
        self.query_exc = query_exc
        self.calls: list[tuple] = []

    def decode_pay_req(self, bolt11: str) -> dict:
        self.calls.append(("decode_pay_req", bolt11))
        return {}

    def query_routes(self, dest: str, amount_sats: int) -> dict:
        self.calls.append(("query_routes", dest, amount_sats))
        if self.query_exc:
            raise self.query_exc
        return self.payload


def _route() -> dict:
    return {
        "routes": [
            {
                "total_fees_msat": 1500,
                "total_amt_msat": 1_001_500,
                "hops": [
                    {"pub_key": _HOP, "chan_id": _CHAN},
                    {"pub_key": _DEST, "chan_id": "111222333"},
                ],
            }
        ],
        "success_prob": 0.42,
    }


def test_route_returns_fees_and_short_hops() -> None:
    reader = _Reader(_route())
    body = json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode()
    out = estimate.handle_request(body, reader)
    dumped = json.dumps(out)
    assert out["total_fees_msat"] == 1500
    assert out["total_amt_msat"] == 1_001_500
    assert out["hop_count"] == 2
    assert out["hops"] == [
        f"{_HOP[:8]}…{_HOP[-4:]}",
        f"{_DEST[:8]}…{_DEST[-4:]}",
    ]
    assert out["success_prob"] == 0.42
    assert _HOP not in dumped
    assert _DEST not in dumped
    assert _CHAN not in dumped
    assert reader.calls == [("query_routes", _DEST, 1000)]


def test_no_route_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = _Reader({"routes": []})
    with pytest.raises(estimate.NoRoute):
        estimate.handle_request(
            json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode(),
            reader,
        )

    def boom(*_args: object, **_kwargs: object) -> dict:
        raise estimate.NoRoute("no_route")

    monkeypatch.setattr(estimate, "handle_request", boom)
    status, _content_type, raw = dispatch(
        _ROUTE,
        method="POST",
        body=json.dumps({"dest_pubkey": _DEST, "amount_sats": 1000}).encode(),
    )
    assert status == 404
    assert json.loads(raw) == {"ok": False, "error": "no_route"}


def test_both_bolt11_and_dest_is_400_before_rpc() -> None:
    reader = _Reader(_route())
    body = json.dumps(
        {"bolt11": _BOLT, "dest_pubkey": _DEST, "amount_sats": 1000}
    ).encode()
    with pytest.raises(estimate.BadInput):
        estimate.handle_request(body, reader)
    assert reader.calls == []


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(estimate, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise estimate.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(estimate, "handle_request", boom)
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
    url = "https://agent-bitcoin.net/paid/lightning/ln-path-estimate"
    needle = 'pathregexp: "^/paid/lightning/ln-path-estimate$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-path-estimate"' in text
        assert text.index('name: "ln-node-info"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    assert "ln_path_estimate.py" in (root / "l402" / "Dockerfile.origin").read_text()
