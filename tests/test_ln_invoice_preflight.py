"""ABT-L402-013 — ln-invoice-preflight policy reasons (no LND)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from l402 import ln_invoice_preflight as pf
from l402.origin import dispatch
from tests.test_ln_invoice_decode import _invoice

_FIXED_NOW = datetime(2026, 9, 7, 20, 30, 0, tzinfo=timezone.utc)


def _body(**kwargs) -> bytes:
    return json.dumps(kwargs).encode("utf-8")


def _post(body: bytes) -> tuple[int, dict]:
    status, _ctype, raw = dispatch(
        "/paid/finance/ln-invoice-preflight", method="POST", body=body
    )
    return status, json.loads(raw)


def test_allow_in_range() -> None:
    out = pf.handle_request(
        _body(bolt11=_invoice(amount_msat=1_000_000)), now=_FIXED_NOW
    )
    assert out["ok"] is True
    assert out["service"] == "ln-invoice-preflight"
    assert out["ttl_s"] == 0
    assert out["allow"] is True
    assert out["reasons"] == []
    assert out["amount_sats"] == 1000
    assert out["expired"] is False
    assert out["network"] == "bitcoin"
    assert "bolt11" not in out


def test_expired() -> None:
    out = pf.handle_request(
        _body(bolt11=_invoice(date=1_000_000_000, expiry=60)), now=_FIXED_NOW
    )
    assert out["allow"] is False
    assert "expired" in out["reasons"]
    assert out["expired"] is True


def test_zero_amount() -> None:
    out = pf.handle_request(_body(bolt11=_invoice(amount_msat=None)), now=_FIXED_NOW)
    assert out["allow"] is False
    assert out["reasons"] == ["zero_amount"]
    assert out["amount_sats"] is None


def test_below_floor() -> None:
    out = pf.handle_request(_body(bolt11=_invoice(amount_msat=50_000)), now=_FIXED_NOW)
    assert out["allow"] is False
    assert out["reasons"] == ["below_floor"]
    assert out["amount_sats"] == 50


def test_above_max_sats() -> None:
    out = pf.handle_request(
        _body(bolt11=_invoice(amount_msat=200_000), max_sats=150),
        now=_FIXED_NOW,
    )
    assert out["allow"] is False
    assert out["reasons"] == ["above_max_sats"]
    assert out["amount_sats"] == 200


def test_network_mismatch() -> None:
    out = pf.handle_request(
        _body(bolt11=_invoice(currency="bc"), network="signet"),
        now=_FIXED_NOW,
    )
    assert out["allow"] is False
    assert out["reasons"] == ["network_mismatch"]
    assert out["network"] == "bitcoin"


def test_multiple_reasons() -> None:
    out = pf.handle_request(
        _body(
            bolt11=_invoice(amount_msat=80_000_000, date=1_000_000_000, expiry=60),
            max_sats=1000,
        ),
        now=_FIXED_NOW,
    )
    assert out["allow"] is False
    assert out["reasons"] == ["expired", "above_max_sats"]
    assert out["amount_sats"] == 80_000


def test_garbage_bolt11_200() -> None:
    status, data = _post(_body(bolt11="lnbc1notvalid"))
    assert status == 200
    assert data["allow"] is False
    assert data["reasons"] == ["bad_invoice"]
    assert data["amount_sats"] is None
    assert "expired" not in data
    assert "network" not in data


def test_missing_bolt11_400() -> None:
    status, data = _post(_body())
    assert status == 400
    assert data == {"ok": False, "error": "missing_bolt11"}


def test_get_405() -> None:
    status, _ctype, raw = dispatch("/paid/finance/ln-invoice-preflight", method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_no_lnd_imports() -> None:
    src = pf.__file__
    assert src
    text = open(src, encoding="utf-8").read()
    assert "import agent_bitcoin.lightning" not in text
    assert "from agent_bitcoin.lightning" not in text
    assert "import lndgrpc" not in text
    assert "from lndgrpc" not in text
    assert "decode_pay_req" not in text
