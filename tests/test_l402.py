"""ABT-L402-001 / ABT-L402-002 — offline L402 header + pay-and-retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent_bitcoin.constants import DEFAULT_L402_PRICE_SATS
from agent_bitcoin.exceptions import PaymentError
from agent_bitcoin.l402.client import (
    L402Client,
    authorization_value,
    parse_www_authenticate,
)
from l402.origin import _payload


def test_payment_result_captures_preimage() -> None:
    from agent_bitcoin.lightning import _payment_result_from_lncli_dict

    result = _payment_result_from_lncli_dict(
        {
            "payment_hash": "aa" * 32,
            "payment_preimage": "bb" * 32,
            "status": "SUCCEEDED",
            "value_sat": "1000",
        }
    )
    assert result.success is True
    assert result.preimage == "bb" * 32
    assert result.amount == 1000


def test_default_l402_price_matches_min_pay() -> None:
    from agent_bitcoin.constants import DEFAULT_MIN_PAYMENT_SATS

    assert DEFAULT_L402_PRICE_SATS == 1_000
    assert DEFAULT_L402_PRICE_SATS == DEFAULT_MIN_PAYMENT_SATS


def test_parse_www_authenticate_aperture() -> None:
    header = 'L402 macaroon="abc+/=", invoice="lnbcrt10u1ptestinvoice"'
    challenge = parse_www_authenticate(header)
    assert challenge.macaroon == "abc+/="
    assert challenge.invoice == "lnbcrt10u1ptestinvoice"


def test_parse_www_authenticate_lsat_alias() -> None:
    header = 'LSAT macaroon="m", invoice="lnbcrt1x"'
    challenge = parse_www_authenticate(header)
    assert challenge.macaroon == "m"
    assert challenge.invoice.startswith("lnbcrt")


def test_header_map_joins_duplicate_www_authenticate() -> None:
    from email.message import Message

    from agent_bitcoin.l402.client import _header_map, _www_authenticate

    msg = Message()
    msg.add_header("Www-Authenticate", 'LSAT macaroon="m", invoice="ln1"')
    msg.add_header("Www-Authenticate", 'L402 macaroon="m", invoice="ln1"')
    mapped = _header_map(msg)
    header = _www_authenticate(mapped)
    assert header
    challenge = parse_www_authenticate(header)
    assert challenge.invoice == "ln1"


def test_parse_www_authenticate_rejects_junk() -> None:
    with pytest.raises(ValueError, match="unrecognized"):
        parse_www_authenticate("Bearer token")
    with pytest.raises(ValueError, match="missing"):
        parse_www_authenticate("")


def test_authorization_value() -> None:
    preimage = "ab" * 32
    assert authorization_value("mac", preimage) == f"L402 mac:{preimage}"
    with pytest.raises(ValueError, match="preimage"):
        authorization_value("mac", "zz")


def test_origin_paths() -> None:
    status, body = _payload("/health")
    assert status == 200
    assert body["ok"] is True
    status, body = _payload("/paid/hello")
    assert status == 200
    assert body["service"] == "l402-demo"
    assert body["msg"] == "hello"
    status, _ = _payload("/other")
    assert status == 404


def test_origin_network_from_env(monkeypatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "signet")
    _, body = _payload("/paid/hello")
    assert body["network"] == "signet"
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    _, body = _payload("/paid/hello")
    assert body["network"] == "mainnet"


def _payer(preimage: str = "cd" * 32) -> MagicMock:
    payer = MagicMock()
    payer.min_payment_sats = 1000
    payer.lnd.decode_pay_req.return_value = {"num_satoshis": "1000"}
    payer.pay_invoice.return_value = MagicMock(
        success=True, preimage=preimage, status="SUCCEEDED"
    )
    return payer


def test_fetch_pays_on_402_and_retries(clear_payment_env) -> None:
    payer = _payer()
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    client = L402Client(payer, expected_price_sats=1000)

    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.side_effect = [
            (402, {"WWW-Authenticate": header}, b"pay"),
            (200, {"Content-Type": "application/json"}, b'{"ok": true}'),
        ]
        resp = client.fetch("http://example.test/paid/hello")

    assert resp.status_code == 200
    assert resp.paid is True
    assert resp.json()["ok"] is True
    payer.pay_invoice.assert_called_once()
    auth_call = mock_get.call_args_list[1]
    got_auth = auth_call.kwargs.get("auth")
    if got_auth is None and len(auth_call.args) > 1:
        got_auth = auth_call.args[1]
    assert got_auth == f"L402 MAC:{'cd' * 32}"


def test_fetch_passthrough_without_402(clear_payment_env) -> None:
    payer = _payer()
    client = L402Client(payer)
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (200, {}, b'{"ok": true, "service": "l402-demo"}')
        resp = client.fetch("http://example.test/health")
    assert resp.status_code == 200
    assert resp.paid is False
    payer.pay_invoice.assert_not_called()


def test_fetch_rejects_wrong_price(clear_payment_env) -> None:
    payer = _payer()
    payer.lnd.decode_pay_req.return_value = {"num_satoshis": "2000"}
    client = L402Client(payer, expected_price_sats=1000)
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (402, {"WWW-Authenticate": header}, b"")
        with pytest.raises(ValueError, match="expected price"):
            client.fetch("http://example.test/paid/hello")
    payer.pay_invoice.assert_not_called()


def test_fetch_rejects_below_minimum(clear_payment_env) -> None:
    payer = _payer()
    payer.lnd.decode_pay_req.return_value = {"num_satoshis": "21"}
    client = L402Client(payer, expected_price_sats=1000)
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (402, {"WWW-Authenticate": header}, b"")
        with pytest.raises(ValueError, match="below minimum"):
            client.fetch("http://example.test/paid/hello")
    payer.pay_invoice.assert_not_called()


def test_fetch_rejects_failed_pay(clear_payment_env) -> None:
    payer = _payer()
    payer.pay_invoice.return_value = MagicMock(success=False, status="FAILED")
    header = 'L402 macaroon="MAC", invoice="lnbcrt1inv"'
    client = L402Client(payer)
    with patch("agent_bitcoin.l402.client.L402Client._get") as mock_get:
        mock_get.return_value = (402, {"WWW-Authenticate": header}, b"")
        with pytest.raises(PaymentError, match="failed"):
            client.fetch("http://example.test/paid/hello")
