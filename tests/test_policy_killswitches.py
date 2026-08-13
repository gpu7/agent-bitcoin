"""Phase 2: mainnet limits, autopay kill-switch, daily spend, fee block."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_bitcoin.constants import (
    DEFAULT_MAINNET_MAX_PAYMENT_SATS,
    DEFAULT_MAX_DAILY_PAYMENT_SATS,
    DEFAULT_MAX_PAYMENT_SATS,
    autopay_allowed,
    fee_send_allowed,
    max_daily_payment_sats,
    max_payment_sats,
)
from agent_bitcoin.spend_ledger import assert_can_spend, record_spend, spent_today_sats


def test_lab_max_payment_default(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    assert max_payment_sats() == DEFAULT_MAX_PAYMENT_SATS
    assert max_daily_payment_sats() == 0
    assert autopay_allowed() is True
    assert fee_send_allowed() is True


def test_mainnet_pilot_defaults(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    assert max_payment_sats() == DEFAULT_MAINNET_MAX_PAYMENT_SATS
    assert max_daily_payment_sats() == DEFAULT_MAX_DAILY_PAYMENT_SATS
    assert autopay_allowed() is False
    assert fee_send_allowed() is False


def test_mainnet_autopay_requires_flag(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_AUTOPAY", "1")
    assert autopay_allowed() is True
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET_FEE", "1")
    assert fee_send_allowed() is True


def test_lab_autopay_killswitch(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "signet")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_AUTOPAY", "0")
    assert autopay_allowed() is False


def test_spend_ledger_daily_cap(tmp_path: Path):
    ledger = tmp_path / "ledger.json"
    assert spent_today_sats(ledger) == 0
    assert_can_spend(40_000, 100_000, path=ledger)
    record_spend(40_000, payment_hash="aa", path=ledger)
    assert spent_today_sats(ledger) == 40_000
    assert_can_spend(60_000, 100_000, path=ledger)
    with pytest.raises(ValueError, match="Daily payment limit"):
        assert_can_spend(60_001, 100_000, path=ledger)
    record_spend(60_000, path=ledger)
    assert spent_today_sats(ledger) == 100_000


def test_client_pay_blocked_without_autopay(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        with pytest.raises(RuntimeError, match="ALLOW_AUTOPAY"):
            c.pay_invoice("lntbs1fake")


def test_client_pay_enforces_amount_and_records(
    clear_payment_env, monkeypatch, tmp_path
):
    monkeypatch.setenv("LND_NETWORK", "signet")
    monkeypatch.setenv("MAX_DAILY_PAYMENT_SATS", "100000")
    monkeypatch.setenv("AGENT_BITCOIN_SPEND_LEDGER", str(tmp_path / "s.json"))
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_lnd = MagicMock()
        mock_lnd.decode_pay_req.return_value = {"num_satoshis": "2000"}
        mock_lnd.pay_invoice.return_value = MagicMock(
            success=True, payment_hash="ph", amount=2000, status="SUCCEEDED"
        )
        mock_cls.return_value = mock_lnd
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        r = c.pay_invoice("lntbs20u1test")
        assert r.success is True
        assert spent_today_sats(tmp_path / "s.json") == 2000


def test_client_fee_blocked_on_mainnet(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    monkeypatch.setenv("FEE_WALLET_ADDRESS", "bc1qtest")
    with patch("agent_bitcoin.client.LNDClient") as mock_cls:
        mock_cls.return_value = MagicMock()
        from agent_bitcoin.client import AgentBitcoinClient

        c = AgentBitcoinClient()
        with pytest.raises(RuntimeError, match="MAINNET_FEE"):
            c.send_onchain("bc1qtest", 21)
