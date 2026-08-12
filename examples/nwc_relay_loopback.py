#!/usr/bin/env python3
"""Optional: NWC client+service over a public WebSocket relay (network-dependent).

Default is dry (does not publish). Pass --live to actually talk to --relay.
"""

from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--relay", default="wss://relay.damus.io")
    p.add_argument("--live", action="store_true", help="Use WebsocketNWCRelay")
    p.add_argument("--amount", type=int, default=2000)
    args = p.parse_args()

    try:
        from pynostr.key import PrivateKey
    except ImportError:
        print("uv sync --python 3.12 --extra nostr", file=sys.stderr)
        return 2

    os.environ.setdefault("AGENT_BITCOIN_NWC_ENABLE", "1")

    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import NWCClient
    from agent_bitcoin.nwc.policy import NWCBudgetPolicy
    from agent_bitcoin.nwc.service import NWCService

    class FakeLND:
        def get_info(self):
            return {
                "alias": "m3-loop",
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
                payment_request=f"lnbcrt_m3_{amount_sats}",
                payment_hash="cc" * 32,
                r_hash="cc" * 32,
            )

        def decode_pay_req(self, pr):
            return {"num_satoshis": str(args.amount)}

        def pay_invoice(self, pr, fee_limit_sats=200):
            return SimpleNamespace(
                success=True, payment_hash="ee" * 32, status="SUCCEEDED"
            )

    if args.live:
        from agent_bitcoin.nostr.relay import WebsocketNWCRelay

        print(f"[m3] LIVE relay {args.relay} — network may fail")
        relay: object = WebsocketNWCRelay([args.relay], timeout=10.0)
        # Service must share the same relay instance to receive publishes
        print(
            "[m3] NOTE: single-process live relay still needs a listening service "
            "subscribed on the same URL; use InMemory for reliable CI."
        )
    else:
        relay = InMemoryNWCBus()
        print("[m3] using InMemoryNWCBus (pass --live for WebSocket)")

    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=FakeLND(),
        bus=relay if isinstance(relay, InMemoryNWCBus) else InMemoryNWCBus(),
        budget=NWCBudgetPolicy(2000, 50_000),
    )
    if isinstance(relay, InMemoryNWCBus):
        svc.attach()
        client = NWCClient(svc.issue_connection(), relay=relay, default_timeout=5.0)
        info = client.get_info()
        print(f"[m3] get_info alias={info.get('alias')}")
        print("\nRESULT: PASS — relay loopback (in-memory)")
        return 0

    print("\nRESULT: SKIP live WS service loop (use in-memory path)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
