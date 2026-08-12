"""M3 primitives: NIP-46, NIP-17, swarm registry (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_bitcoin.nostr.swarm import SwarmAgent, SwarmRegistry


def test_swarm_registry_roundtrip(tmp_path: Path) -> None:
    reg = SwarmRegistry(
        [
            SwarmAgent(
                name="alice",
                npub="npub1alice",
                role="payer",
                relays=["wss://r"],
            ),
            SwarmAgent(name="bob", npub="npub1bob", role="invoice"),
        ]
    )
    assert len(reg.list(role="payer")) == 1
    p = tmp_path / "swarm.json"
    reg.save(p)
    loaded = SwarmRegistry.load(p)
    assert loaded.get("alice") is not None
    assert loaded.get("alice").role == "payer"
    profile = json.loads(loaded.get("bob").profile_content())
    assert profile["agent_bitcoin"]["role"] == "invoice"


def test_nip46_sign_and_policy() -> None:
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    from agent_bitcoin.nostr.nip46 import Nip46Bunker, Nip46Client

    user = PrivateKey()
    bunker = Nip46Bunker(user, allowed_kinds=frozenset({1}))
    client = Nip46Client(bunker)
    assert client.call("ping") == "ack"
    assert client.call("get_public_key") == user.public_key.hex()
    methods = client.call("describe")
    assert "sign_event" in methods
    signed = client.call("sign_event", [{"kind": 1, "content": "hello-m3", "tags": []}])
    assert signed["pubkey"] == user.public_key.hex()
    assert signed["sig"]
    with pytest.raises(Exception):
        client.call("sign_event", [{"kind": 7, "content": "denied", "tags": []}])


def test_nip17_wrap_unwrap() -> None:
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    from agent_bitcoin.nostr.nip17 import gift_unwrap, gift_wrap

    alice = PrivateKey()
    bob = PrivateKey()
    wrap = gift_wrap(alice, bob.public_key.hex(), "secret invoice handoff")
    assert wrap["kind"] == 1059
    rumor = gift_unwrap(bob, wrap)
    assert rumor["content"] == "secret invoice handoff"
    assert rumor["pubkey"] == alice.public_key.hex()
