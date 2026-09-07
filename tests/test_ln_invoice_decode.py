"""ABT-L402-012 — ln-invoice-decode in-process BOLT11 (no LND)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

import pytest
from bolt11 import MilliSatoshi, TagChar, Tags, encode
from bolt11.types import Bolt11

from l402 import ln_invoice_decode as dec
from l402.origin import dispatch

_FIXED_NOW = datetime(2026, 9, 7, 20, 0, 0, tzinfo=timezone.utc)
_PRIV = "11" * 32
_HASH = "aa" * 32
_SECRET = "bb" * 32


def _invoice(
    *,
    currency: str = "bc",
    amount_msat: int | None = 1_000_000,
    date: int = 2_000_000_000,
    expiry: int | None = None,
    description: str = "coffee",
) -> str:
    tags = Tags()
    tags.add(TagChar.payment_hash, _HASH)
    tags.add(TagChar.payment_secret, _SECRET)
    if description is not None:
        tags.add(TagChar.description, description)
    if expiry is not None:
        tags.add(TagChar.expire_time, expiry)
    kwargs: dict = {"currency": currency, "date": date, "tags": tags}
    if amount_msat is not None:
        kwargs["amount_msat"] = MilliSatoshi(amount_msat)
    return encode(Bolt11(**kwargs), private_key=_PRIV)


def _body(bolt11: str | None = "", **extra) -> bytes:
    payload: dict = dict(extra)
    if bolt11 is not None:
        payload["bolt11"] = bolt11
    return json.dumps(payload).encode("utf-8")


def test_bitcoin_1000_sats() -> None:
    raw = _invoice()
    out = dec.handle_request(_body(raw), now=_FIXED_NOW)
    assert out["ok"] is True
    assert out["service"] == "ln-invoice-decode"
    assert out["source"] == "local_bolt11"
    assert out["ttl_s"] == 0
    assert out["stale"] is False
    assert out["network"] == "bitcoin"
    assert out["amount_sats"] == 1000
    assert out["dest_pubkey"] == out["dest_pubkey"].lower()
    assert len(out["dest_pubkey"]) == 66
    assert out["payment_hash"] == _HASH
    assert out["expiry_unix"] == 2_000_000_000 + 3600
    assert out["expired"] is False
    assert out["description"] == "coffee"
    assert "bolt11" not in out
    assert "route_hints" not in out


@pytest.mark.parametrize(
    ("currency", "network"),
    (
        ("bc", "bitcoin"),
        ("tb", "testnet"),
        ("tbs", "signet"),
        ("bcrt", "regtest"),
    ),
)
def test_network_mapping(currency: str, network: str) -> None:
    out = dec.handle_request(_body(_invoice(currency=currency)), now=_FIXED_NOW)
    assert out["network"] == network


def test_zero_amount_null() -> None:
    out = dec.handle_request(_body(_invoice(amount_msat=None)), now=_FIXED_NOW)
    assert out["amount_sats"] is None


def test_expired_true_vs_false() -> None:
    past = _invoice(date=1_000_000_000, expiry=60)
    out = dec.handle_request(_body(past), now=_FIXED_NOW)
    assert out["expired"] is True
    future = _invoice(date=2_000_000_000, expiry=3600)
    out2 = dec.handle_request(_body(future), now=_FIXED_NOW)
    assert out2["expired"] is False


def test_long_description_omitted() -> None:
    out = dec.handle_request(_body(_invoice(description="x" * 201)), now=_FIXED_NOW)
    assert "description" not in out


def test_origin_400_invalid() -> None:
    status, _ctype, body = dispatch(
        "/paid/finance/ln-invoice-decode",
        method="POST",
        body=_body("not-an-invoice"),
    )
    assert status == 400
    assert json.loads(body) == {"ok": False, "error": "bad_invoice"}


def test_origin_400_empty() -> None:
    status, _ctype, body = dispatch(
        "/paid/finance/ln-invoice-decode", method="POST", body=b"{}"
    )
    assert status == 400
    assert json.loads(body)["error"] == "bad_invoice"


def test_get_405() -> None:
    status, _ctype, body = dispatch("/paid/finance/ln-invoice-decode", method="GET")
    assert status == 405
    assert json.loads(body) == {"ok": False, "error": "method_not_allowed"}


def test_origin_200(monkeypatch) -> None:
    payload = {
        "ok": True,
        "service": "ln-invoice-decode",
        "amount_sats": 1000,
        "payment_hash": _HASH,
        "dest_pubkey": "02" + "ab" * 32,
    }
    monkeypatch.setattr(dec, "handle_request", lambda *_a, **_k: payload)
    status, ctype, body = dispatch(
        "/paid/finance/ln-invoice-decode",
        method="POST",
        body=_body(_invoice()),
    )
    assert status == 200
    assert ctype == "application/json"
    data = json.loads(body)
    assert data["amount_sats"] == 1000
    assert data["payment_hash"] == _HASH


def test_handler_does_not_import_lnd() -> None:
    src = dec.__file__
    assert src
    text = open(src, encoding="utf-8").read()
    assert "import agent_bitcoin.lightning" not in text
    assert "from agent_bitcoin.lightning" not in text
    assert "import lndgrpc" not in text
    assert "from lndgrpc" not in text
    assert "decode_pay_req" not in text
    assert "l402.ln_invoice_decode" in sys.modules
