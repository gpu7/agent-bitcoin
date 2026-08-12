"""N3: NWC client + mock wallet over in-memory bus (no relays / no LND)."""

from __future__ import annotations

import secrets

import pytest

pynostr = pytest.importorskip("pynostr")
from pynostr.key import PrivateKey  # noqa: E402

from agent_bitcoin.nwc import NWCError, build_nwc_uri, parse_nwc_uri  # noqa: E402
from agent_bitcoin.nwc.bus import InMemoryNWCBus  # noqa: E402
from agent_bitcoin.nwc.client import NWCClient, attach_mock_wallet  # noqa: E402
from agent_bitcoin.nwc.crypto import nip04_decrypt, nip04_encrypt  # noqa: E402


def _connection_and_wallet() -> tuple[str, PrivateKey, InMemoryNWCBus]:
    wallet_sk = PrivateKey()
    client_secret = secrets.token_hex(32)
    uri = build_nwc_uri(
        wallet_sk.public_key.hex(),
        secret=client_secret,
        relays=["wss://relay.example.invalid"],
    )
    bus = InMemoryNWCBus()
    attach_mock_wallet(bus, wallet_sk)
    return uri, wallet_sk, bus


def test_nip04_roundtrip() -> None:
    a = PrivateKey()
    b = PrivateKey()
    ct = nip04_encrypt(a.hex(), b.public_key.hex(), "hello-nwc")
    assert nip04_decrypt(b.hex(), a.public_key.hex(), ct) == "hello-nwc"


def test_client_get_info_and_balance() -> None:
    uri, _wallet, bus = _connection_and_wallet()
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    info = client.get_info()
    assert info["alias"] == "agent-bitcoin-mock-nwc"
    assert "pay_invoice" in info["methods"]
    bal = client.get_balance()
    assert bal["balance"] == 1_000_000_000


def test_client_make_and_pay_invoice() -> None:
    uri, _wallet, bus = _connection_and_wallet()
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    inv = client.make_invoice(2000, description="n3-test")
    assert inv["amount"] == 2_000_000
    assert inv["invoice"].startswith("lnt_mock_")
    paid = client.pay_invoice(inv["invoice"])
    assert paid["preimage"]
    assert paid.get("fees_paid") == 0


def test_client_rejects_low_amount() -> None:
    uri, _wallet, bus = _connection_and_wallet()
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    with pytest.raises(Exception, match="minimum|below"):
        client.make_invoice(1)


def test_client_denied_method_via_call() -> None:
    uri, _wallet, bus = _connection_and_wallet()
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    with pytest.raises(Exception):
        client.call("multi_pay_invoice", {})


def test_parse_uri_matches_client_pubkey() -> None:
    uri, wallet_sk, bus = _connection_and_wallet()
    conn = parse_nwc_uri(uri)
    client = NWCClient(conn, relay=bus)
    # client pubkey is derived from secret, not wallet
    assert client.client_pubkey != wallet_sk.public_key.hex()
    assert len(client.client_pubkey) == 64


def test_custom_handler_error() -> None:
    wallet_sk = PrivateKey()
    client_secret = secrets.token_hex(32)
    uri = build_nwc_uri(
        wallet_sk.public_key.hex(),
        secret=client_secret,
        relays=["wss://r"],
    )
    bus = InMemoryNWCBus()

    def boom(_params):
        raise RuntimeError("wallet offline")

    attach_mock_wallet(bus, wallet_sk, handlers={"get_info": boom})
    client = NWCClient(uri, relay=bus, default_timeout=2.0)
    with pytest.raises(NWCError, match="INTERNAL|offline"):
        client.get_info()
