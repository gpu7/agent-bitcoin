"""
Live LND SDK integration tests (regtest or signet).

Offline unit suite does not need these. Run explicitly:

  LND_NETWORK=signet uv run pytest tests/test_lnd_sdk_integration.py -m integration -v

Requires Docker and unlocked LND container(s) on this host.
Dual-node pay needs *both* payer and receiver containers running locally
(typical lab has Mac peer on Mac, AWS agent on AWS — dual pay then skips).
"""

from __future__ import annotations

import os

import pytest

from tests.network_config import (
    container_running,
    make_lnd_client,
    resolve_network,
    stack_for,
)

pytestmark = pytest.mark.integration


def _network() -> str:
    return resolve_network(os.getenv("LND_NETWORK"))


@pytest.fixture
def stack():
    return stack_for(_network())


@pytest.fixture
def local_agent_or_peer(stack):
    """Prefer agent container if up, else peer — for single-node smoke."""
    for name in (stack.agent_container, stack.peer_container):
        if container_running(name):
            return name
    pytest.skip(
        f"No LND container running for network={stack.network} "
        f"(tried {stack.agent_container}, {stack.peer_container})"
    )


def test_getinfo_network_and_unlocked(stack, local_agent_or_peer):
    client = make_lnd_client(local_agent_or_peer, stack.network)
    info = client._run("getinfo")
    assert info.get("identity_pubkey"), info
    # chains[0].network may be 'bitcoin' with chains; lncli uses --network flag
    assert info.get("synced_to_chain") is True, (
        f"expected synced_to_chain on {local_agent_or_peer}: {info}"
    )


def test_channel_balance_readable(stack, local_agent_or_peer):
    client = make_lnd_client(local_agent_or_peer, stack.network)
    bal = client.get_channel_balance()
    assert bal.local_balance >= 0
    assert bal.remote_balance >= 0


def test_create_invoice_via_sdk(stack, local_agent_or_peer, payment_limits):
    client = make_lnd_client(local_agent_or_peer, stack.network)
    # Use min payment so policy matches AgentBitcoinClient defaults if wrapped later
    amount = payment_limits["min"]
    inv = client.create_invoice(
        memo=f"pytest-{stack.network}",
        amount_sats=amount,
        expiry_seconds=600,
    )
    assert inv.payment_request, inv
    # BOLT11 prefixes: regtest lnbcrt, signet lntbs, testnet lntb, mainnet lnbc
    prefix = inv.payment_request[:5]
    if stack.network == "regtest":
        assert inv.payment_request.startswith("lnbcrt"), prefix
    elif stack.network == "signet":
        assert inv.payment_request.startswith("lntbs"), prefix
    else:
        assert inv.payment_request.startswith("ln"), prefix
    assert inv.r_hash


def test_dual_node_sdk_pay_when_both_local(stack, payment_limits):
    """Mac create + AWS pay (signet) or AWS create + Mac pay (regtest defaults)."""
    recv = stack.receiver_container
    pay = stack.payer_container
    if not container_running(recv):
        pytest.skip(f"receiver container not running: {recv}")
    if not container_running(pay):
        pytest.skip(
            f"payer container not running on this host: {pay} "
            f"(dual-node pay needs both containers locally, or run pay on the payer host)"
        )
    if recv == pay:
        pytest.skip("receiver and payer are the same container")

    amount = payment_limits["min"]
    receiver = make_lnd_client(recv, stack.network)
    payer = make_lnd_client(pay, stack.network)

    # Channel should be active on payer for outbound
    chans = payer._run("listchannels")
    channels = chans.get("channels") or []
    active = [c for c in channels if c.get("active")]
    if not active:
        pytest.skip(f"no active channel on payer {pay}")

    before = payer.get_channel_balance()
    if before.local_balance < amount + 500:
        pytest.skip(
            f"payer local_balance {before.local_balance} too low for {amount} sat"
        )

    inv = receiver.create_invoice(
        memo=f"pytest-dual-{stack.network}",
        amount_sats=amount,
        expiry_seconds=600,
    )
    result = payer.pay_invoice(inv.payment_request, fee_limit_sats=500)
    assert result.success is True, result
    assert result.status.upper() in {"SUCCEEDED", "SUCCESS", "COMPLETE", "COMPLETED"}

    after = payer.get_channel_balance()
    assert after.local_balance <= before.local_balance
    # Expect about `amount` moved (allow small fee variance — fee often 0 on direct)
    assert before.local_balance - after.local_balance >= amount - 10
