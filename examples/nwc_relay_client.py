#!/usr/bin/env python3
"""Mac: NWC client over public relays (NIP-44).

  export NWC_URL='nostr+walletconnect://…'   # from AWS service
  uv run --python 3.12 python examples/nwc_relay_client.py --method get_info

Pay (mainnet, 2k, after go):
  export AGENT_BITCOIN_ALLOW_MAINNET=1
  export AGENT_BITCOIN_NWC_ENABLE=1
  export AGENT_BITCOIN_NWC_ALLOW_MAINNET=1
  uv run --python 3.12 python examples/nwc_relay_client.py \\
    --method pay --amount 2000 --yes-mainnet
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--method",
        default="get_info",
        choices=["get_info", "get_balance", "invoice", "pay"],
    )
    p.add_argument("--amount", type=int, default=2000)
    p.add_argument("--memo", default="nwc-relay-client")
    p.add_argument("--invoice", default="", help="bolt11 for --method pay")
    p.add_argument("--yes-mainnet", action="store_true")
    p.add_argument(
        "--memory",
        action="store_true",
        help="Use InMemory bus (dev). Default: public WebsocketNWCRelay from URI",
    )
    args = p.parse_args()

    uri = os.getenv("NWC_URL", "").strip()
    if not uri:
        print("Set NWC_URL to the URI printed by nwc_relay_service.py", file=sys.stderr)
        return 2

    try:
        from agent_bitcoin.nwc.uri import parse_nwc_uri
        from agent_bitcoin.nwc.client import NWCClient
    except ImportError:
        print("uv sync --python 3.12 --extra nostr", file=sys.stderr)
        return 2

    conn = parse_nwc_uri(uri)
    print(f"[mac] wallet={conn.wallet_pubkey[:16]}… relays={list(conn.relays)}")

    if args.memory:
        from agent_bitcoin.nwc.bus import InMemoryNWCBus

        relay = InMemoryNWCBus()
        print("[mac] InMemoryNWCBus (no public relay)")
    else:
        from agent_bitcoin.nostr.relay import WebsocketNWCRelay

        relay = WebsocketNWCRelay(conn.relays, timeout=20.0)
        print("[mac] public WebsocketNWCRelay")
        print(
            "[mac] AWS must already show 'subscribed, polling' (else this times out at 30s)"
        )

    client = NWCClient(conn, relay=relay, default_timeout=30.0)

    if args.method == "get_info":
        print("[mac] get_info: publish 23194, wait ≤30s for 23195", flush=True)
        print(client.get_info())
        return 0
    if args.method == "get_balance":
        print(client.get_balance())
        return 0
    if args.method == "invoice":
        print(client.make_invoice(args.amount, description=args.memo))
        return 0
    if args.method == "pay":
        if os.getenv("LND_NETWORK", "").lower() == "mainnet" and not args.yes_mainnet:
            print("Pass --yes-mainnet for mainnet pay (max 2k).", file=sys.stderr)
            return 2
        if not args.invoice:
            print("--invoice bolt11 required for pay", file=sys.stderr)
            return 2
        print(client.pay_invoice(args.invoice, amount_sats=args.amount))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
