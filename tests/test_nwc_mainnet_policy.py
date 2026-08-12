"""N6: mainnet NWC latches and tight budget defaults."""

from __future__ import annotations

import pytest

from agent_bitcoin.nwc.errors import NWCPolicyError
from agent_bitcoin.nwc.policy import (
    DEFAULT_NWC_MAINNET_MAX_SATS,
    NWCBudgetPolicy,
    assert_nwc_network_allowed,
    nwc_mainnet_allowed,
)


def test_mainnet_budget_default_is_tight(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.delenv("NWC_MAX_PAYMENT_SATS", raising=False)
    monkeypatch.delenv("MAX_PAYMENT_SATS", raising=False)
    pol = NWCBudgetPolicy.from_env()
    assert pol.max_sats == DEFAULT_NWC_MAINNET_MAX_SATS
    assert pol.max_sats == 2_000


def test_mainnet_budget_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("NWC_MAX_PAYMENT_SATS", "2000")
    monkeypatch.setenv("NWC_MIN_PAYMENT_SATS", "2000")
    pol = NWCBudgetPolicy.from_env()
    assert pol.min_sats == 2000
    assert pol.max_sats == 2000


def test_lab_budget_not_forced_to_2k(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LND_NETWORK", "regtest")
    monkeypatch.delenv("NWC_MAX_PAYMENT_SATS", raising=False)
    pol = NWCBudgetPolicy.from_env()
    # lab may be 1_000_000 default; at least not forced to 2k only by mainnet path
    assert pol.max_sats >= 2_000


def test_assert_nwc_network_lab_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LND_NETWORK", "regtest")
    assert_nwc_network_allowed()  # no raise


def test_assert_nwc_network_mainnet_requires_latches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.delenv("AGENT_BITCOIN_NWC_ENABLE", raising=False)
    monkeypatch.delenv("AGENT_BITCOIN_NWC_ALLOW_MAINNET", raising=False)
    monkeypatch.delenv("AGENT_BITCOIN_ALLOW_MAINNET", raising=False)
    with pytest.raises(NWCPolicyError, match="NWC_ENABLE"):
        assert_nwc_network_allowed()

    monkeypatch.setenv("AGENT_BITCOIN_NWC_ENABLE", "1")
    with pytest.raises(NWCPolicyError, match="NWC_ALLOW_MAINNET"):
        assert_nwc_network_allowed()
    assert nwc_mainnet_allowed() is False

    monkeypatch.setenv("AGENT_BITCOIN_NWC_ALLOW_MAINNET", "1")
    with pytest.raises(NWCPolicyError, match="ALLOW_MAINNET"):
        assert_nwc_network_allowed()

    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    assert_nwc_network_allowed()
    assert nwc_mainnet_allowed() is True


def test_service_blocks_mainnet_without_latch(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import NWCClient
    from agent_bitcoin.nwc.errors import NWCError
    from agent_bitcoin.nwc.service import NWCService
    from types import SimpleNamespace

    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("AGENT_BITCOIN_NWC_ENABLE", "1")
    monkeypatch.delenv("AGENT_BITCOIN_NWC_ALLOW_MAINNET", raising=False)
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")

    class FakeLND:
        def get_info(self):
            return {
                "alias": "m",
                "identity_pubkey": "aa" * 32,
                "chains": [{"network": "mainnet"}],
                "block_height": 1,
                "block_hash": "bb" * 32,
            }

        def get_channel_balance(self):
            return SimpleNamespace(local_balance=10_000, remote_balance=0)

        def get_balance(self):
            return SimpleNamespace(confirmed_balance="0")

        def create_invoice(self, *a, **k):
            raise AssertionError("should not create")

        def decode_pay_req(self, pr):
            return {"num_satoshis": "2000"}

        def pay_invoice(self, *a, **k):
            raise AssertionError("should not pay")

    bus = InMemoryNWCBus()
    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=FakeLND(),
        bus=bus,
        budget=NWCBudgetPolicy.mainnet_tight(),
        require_enable=True,
    )
    svc.attach()
    client = NWCClient(svc.issue_connection(), relay=bus, default_timeout=2.0)
    with pytest.raises(NWCError, match="NWC_ALLOW_MAINNET|RESTRICTED"):
        client.get_info()
