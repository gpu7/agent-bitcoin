"""N4: NWC service with fake LND backend (no Docker required)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pynostr = pytest.importorskip("pynostr")
from pynostr.key import PrivateKey  # noqa: E402

from agent_bitcoin.nwc import NWCError  # noqa: E402
from agent_bitcoin.nwc.bus import InMemoryNWCBus  # noqa: E402
from agent_bitcoin.nwc.client import NWCClient  # noqa: E402
from agent_bitcoin.nwc.policy import NWCBudgetPolicy  # noqa: E402
from agent_bitcoin.nwc.service import NWCService  # noqa: E402


class FakeLND:
    def __init__(self) -> None:
        self.invoices: list[tuple[str, int]] = []
        self.pays: list[str] = []
        self.local_sats = 100_000
        self.wallet_sats = 50_000

    def get_info(self) -> dict:
        return {
            "alias": "fake-lnd",
            "identity_pubkey": "aa" * 32,
            "block_height": 100,
            "block_hash": "bb" * 32,
            "color": "#112233",
            "chains": [{"chain": "bitcoin", "network": "regtest"}],
        }

    def get_channel_balance(self):
        return SimpleNamespace(local_balance=self.local_sats, remote_balance=20_000)

    def get_balance(self):
        return SimpleNamespace(
            total_balance=str(self.wallet_sats),
            confirmed_balance=str(self.wallet_sats),
            unconfirmed_balance="0",
        )

    def create_invoice(self, memo: str, amount_sats: int, expiry_seconds: int = 3600):
        self.invoices.append((memo, amount_sats))
        return SimpleNamespace(
            payment_request=f"lnbcrt_fake_{amount_sats}",
            r_hash="cc" * 32,
            payment_hash="cc" * 32,
        )

    def decode_pay_req(self, payment_request: str) -> dict:
        # lnbcrt_fake_2000
        amt = 2000
        if "_fake_" in payment_request:
            try:
                amt = int(payment_request.rsplit("_", 1)[-1])
            except ValueError:
                pass
        return {"num_satoshis": str(amt), "payment_hash": "dd" * 32}

    def pay_invoice(self, payment_request: str, fee_limit_sats: int = 200):
        self.pays.append(payment_request)
        self.local_sats = max(0, self.local_sats - 2000)
        return SimpleNamespace(
            success=True,
            payment_hash="ee" * 32,
            amount=2000,
            status="SUCCEEDED",
        )


@pytest.fixture()
def service_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AGENT_BITCOIN_NWC_ENABLE", "1")
    bus = InMemoryNWCBus()
    lnd = FakeLND()
    wallet_sk = PrivateKey()
    svc = NWCService(
        wallet_sk=wallet_sk,
        lnd=lnd,
        bus=bus,
        budget=NWCBudgetPolicy(min_sats=2000, max_sats=50_000),
        require_enable=True,
    )
    svc.attach()
    uri = svc.issue_connection(relays=["wss://relay.example.invalid"])
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    return svc, client, lnd


def test_service_get_info_and_balance(service_client) -> None:
    _svc, client, lnd = service_client
    info = client.get_info()
    assert info["alias"] == "fake-lnd"
    assert info["network"] == "regtest"
    assert "pay_invoice" in info["methods"]
    bal = client.get_balance()
    assert bal["balance"] == (lnd.local_sats + lnd.wallet_sats) * 1000


def test_service_make_and_pay_invoice(service_client) -> None:
    _svc, client, lnd = service_client
    from agent_bitcoin.constants import fee_amount_sats

    inv = client.make_invoice(2000, description="n4-test")
    billed = 2000 + fee_amount_sats()
    assert inv["invoice"] == f"lnbcrt_fake_{billed}"
    assert inv["amount"] == billed * 1000
    assert lnd.invoices[-1] == ("n4-test", billed)
    paid = client.pay_invoice(inv["invoice"])
    assert paid["preimage"]
    assert lnd.pays == [f"lnbcrt_fake_{billed}"]


def test_service_disabled_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_BITCOIN_NWC_ENABLE", raising=False)
    bus = InMemoryNWCBus()
    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=FakeLND(),
        bus=bus,
        budget=NWCBudgetPolicy(2000, 50_000),
        require_enable=True,
    )
    svc.attach()
    uri = svc.issue_connection()
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    with pytest.raises(NWCError, match="RESTRICTED|disabled"):
        client.get_info()


def test_unauthorized_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_BITCOIN_NWC_ENABLE", "1")
    bus = InMemoryNWCBus()
    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=FakeLND(),
        bus=bus,
        budget=NWCBudgetPolicy(2000, 50_000),
    )
    svc.attach()
    # URI not issued by this service → client not authorized
    from agent_bitcoin.nwc import build_nwc_uri
    import secrets

    rogue = build_nwc_uri(
        svc.wallet_pubkey,
        secret=secrets.token_hex(32),
        relays=["wss://r"],
    )
    client = NWCClient(rogue, relay=bus, default_timeout=2.0)
    with pytest.raises(NWCError, match="UNAUTHORIZED|not authorized"):
        client.get_info()


def test_amount_below_minimum(service_client) -> None:
    _svc, client, _lnd = service_client
    with pytest.raises(Exception, match="minimum|below"):
        client.make_invoice(100)
