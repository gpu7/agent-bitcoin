"""N5: decision gate → NWC pay helpers (offline)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_bitcoin.nwc.flow import (
    decision_is_pay,
    nwc_pay_if_approved,
    rule_based_decision,
)


def test_decision_is_pay_variants() -> None:
    assert decision_is_pay("PAY") is True
    assert decision_is_pay("pay") is True
    assert decision_is_pay("REJECT") is False
    assert decision_is_pay({"decision": "PAY"}) is True
    assert decision_is_pay({"pay": True}) is True
    assert decision_is_pay({"pay": False}) is False
    assert decision_is_pay(SimpleNamespace(pay=True)) is True
    assert decision_is_pay(SimpleNamespace(decision="REJECT")) is False


def test_rule_based_within_bounds() -> None:
    d = rule_based_decision(2000, min_sats=2000, max_sats=50_000)
    assert d["pay"] is True
    assert d["decision"] == "PAY"


def test_rule_based_rejects_low_and_high() -> None:
    assert rule_based_decision(1, min_sats=2000, max_sats=50_000)["pay"] is False
    assert rule_based_decision(100_000, min_sats=2000, max_sats=50_000)["pay"] is False


def test_nwc_pay_if_approved_skips_on_reject() -> None:
    class Client:
        def pay_invoice(self, invoice, amount_sats=None):
            raise AssertionError("should not pay")

    assert nwc_pay_if_approved(Client(), "REJECT", "lnbc1...") is None


def test_nwc_pay_if_approved_calls_client() -> None:
    class Client:
        def __init__(self):
            self.called = None

        def pay_invoice(self, invoice, amount_sats=None):
            self.called = (invoice, amount_sats)
            return {"preimage": "ab" * 32}

    c = Client()
    out = nwc_pay_if_approved(c, {"decision": "PAY"}, "lnbc1abc", amount_sats=2000)
    assert out == {"preimage": "ab" * 32}
    assert c.called == ("lnbc1abc", 2000)


def test_end_to_end_rule_then_nwc(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import NWCClient
    from agent_bitcoin.nwc.policy import NWCBudgetPolicy
    from agent_bitcoin.nwc.service import NWCService

    monkeypatch.setenv("AGENT_BITCOIN_NWC_ENABLE", "1")

    class FakeLND:
        def get_info(self):
            return {
                "alias": "t",
                "identity_pubkey": "aa" * 32,
                "chains": [{"network": "regtest"}],
                "block_height": 1,
                "block_hash": "bb" * 32,
            }

        def get_channel_balance(self):
            return SimpleNamespace(local_balance=50_000, remote_balance=0)

        def get_balance(self):
            return SimpleNamespace(confirmed_balance="0")

        def create_invoice(self, memo, amount_sats, expiry_seconds=3600):
            return SimpleNamespace(
                payment_request=f"lnbcrt_x_{amount_sats}",
                payment_hash="cc" * 32,
                r_hash="cc" * 32,
            )

        def decode_pay_req(self, pr):
            return {"num_satoshis": "2000"}

        def pay_invoice(self, pr, fee_limit_sats=200):
            return SimpleNamespace(
                success=True, payment_hash="ee" * 32, status="SUCCEEDED"
            )

    bus = InMemoryNWCBus()
    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=FakeLND(),
        bus=bus,
        budget=NWCBudgetPolicy(2000, 50_000),
    )
    svc.attach()
    client = NWCClient(svc.issue_connection(), relay=bus, default_timeout=2.0)
    decision = rule_based_decision(2000)
    inv = client.make_invoice(2000, description="n5")
    paid = nwc_pay_if_approved(client, decision, inv["invoice"])
    assert paid is not None
    assert paid.get("preimage")
