"""M3 swarm primitives: NIP-46, NIP-17, registry, optional WebSocket relays."""

from agent_bitcoin.nostr.swarm import SwarmAgent, SwarmRegistry

__all__ = ["SwarmAgent", "SwarmRegistry"]

try:
    from agent_bitcoin.nostr.nip17 import gift_unwrap, gift_wrap
    from agent_bitcoin.nostr.nip46 import Nip46Bunker, Nip46Client
    from agent_bitcoin.nostr.relay import WebsocketNWCRelay

    __all__ += [
        "Nip46Bunker",
        "Nip46Client",
        "WebsocketNWCRelay",
        "gift_unwrap",
        "gift_wrap",
    ]
except ImportError:  # pragma: no cover
    pass
