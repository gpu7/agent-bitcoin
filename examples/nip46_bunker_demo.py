#!/usr/bin/env python3
"""M3: NIP-46 bunker + client (in-process, no public relay)."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from pynostr.key import PrivateKey
    except ImportError:
        print("uv sync --python 3.12 --extra nostr", file=sys.stderr)
        return 2

    from agent_bitcoin.nostr.nip46 import Nip46Bunker, Nip46Client

    user = PrivateKey()
    bunker = Nip46Bunker(user)
    client = Nip46Client(bunker)
    print(f"[m3] user npub hex={client.call('get_public_key')[:16]}…")
    print(f"[m3] describe={client.call('describe')}")
    ev = client.call("sign_event", [{"kind": 1, "content": "m3-bunker", "tags": []}])
    print(f"[m3] signed id={ev['id'][:16]}… kind={ev['kind']}")
    print("\nRESULT: PASS — NIP-46 bunker demo")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
