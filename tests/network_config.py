"""Shared LND network defaults for regtest and signet integration tests."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkStack:
    network: str
    # Primary agent / payer-heavy node (AWS in dual-node docs)
    agent_container: str
    # Counterparty (Mac)
    peer_container: str
    # Default dual-node roles for product-path smoke:
    # receiver creates invoice; payer has outbound channel liquidity.
    receiver_container: str
    payer_container: str


STACKS = {
    "regtest": NetworkStack(
        network="regtest",
        agent_container="agent-payment-decision-lnd",
        peer_container="agent-bitcoin-lnd",
        # Historical lab: Mac often paid AWS invoices (AWS receives).
        receiver_container="agent-payment-decision-lnd",
        payer_container="agent-bitcoin-lnd",
    ),
    "signet": NetworkStack(
        network="signet",
        agent_container="agent-payment-decision-lnd-signet",
        peer_container="agent-bitcoin-lnd-signet",
        # Proven product path: Mac creates, AWS pays (AWS has outbound).
        receiver_container="agent-bitcoin-lnd-signet",
        payer_container="agent-payment-decision-lnd-signet",
    ),
}


def resolve_network(raw: str | None = None) -> str:
    network = (raw or os.getenv("LND_NETWORK") or "regtest").strip().lower()
    if network not in STACKS:
        raise ValueError(
            f"Unsupported LND_NETWORK={network!r}; expected one of {sorted(STACKS)}"
        )
    return network


def stack_for(network: str | None = None) -> NetworkStack:
    return STACKS[resolve_network(network)]


def container_running(name: str) -> bool:
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def make_lnd_client(container: str, network: str, lnd_dir: str | None = None):
    """Build LND client with explicit container/network (docker transport)."""
    os.environ["LND_TRANSPORT"] = "docker"
    os.environ["LND_CONTAINER"] = container
    os.environ["LND_NETWORK"] = network
    os.environ["LND_DIR"] = (
        lnd_dir or os.getenv("LND_DIR") or "/home/lnd/.lnd"
    ).strip() or "/home/lnd/.lnd"
    from agent_bitcoin.lightning import create_lnd_client

    return create_lnd_client()
