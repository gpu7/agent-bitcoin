"""Default public Nostr relays for NWC (no private relay required)."""

from __future__ import annotations

import os

DEFAULT_PUBLIC_RELAYS: tuple[str, ...] = (
    "wss://relay.damus.io",
    "wss://nos.lol",
)


def public_relays_from_env() -> list[str]:
    raw = os.getenv("NWC_RELAYS", "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip().startswith("wss://")]
    return list(DEFAULT_PUBLIC_RELAYS)
