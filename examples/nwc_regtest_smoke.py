#!/usr/bin/env python3
"""NWC regtest smoke: service (LND) + client over in-memory bus.

Prerequisites:
  - Optional: live LND via docker (default container agent-payment-decision-lnd)
  - AGENT_BITCOIN_NWC_ENABLE=1
  - Python 3.12 + ``uv sync --extra nostr``

Without LND, use --mock for offline path (same as unit tests).

  export AGENT_BITCOIN_NWC_ENABLE=1
  export LND_NETWORK=regtest
  export LND_TRANSPORT=docker
  .venv/bin/python examples/nwc_regtest_smoke.py --mock
  # live (invoice only if no second peer to pay):
  .venv/bin/python examples/nwc_regtest_smoke.py --amount 2000
"""

from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace


def main() -> int:
    parser = argparse.ArgumentParser(description="NWC regtest / mock smoke")
    parser.add_argument("--amount", type=int, default=2000, help="sats (default 2000)")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use FakeLND (no Docker) — offline smoke",
    )
    parser.add_argument(
        "--pay",
        action="store_true",
        help="Also pay the created invoice (needs liquidity / mock)",
    )
    args = parser.parse_args()

    try:
        from pynostr.key import PrivateKey
    except ImportError:
        print(
            "Install nostr extra: uv sync --python 3.12 --extra nostr", file=sys.stderr
        )
        return 2

    os.environ.setdefault("AGENT_BITCOIN_NWC_ENABLE", "1")
    os.environ.setdefault("LND_TRANSPORT", "docker")

    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import NWCClient
    from agent_bitcoin.nwc.policy import NWCBudgetPolicy
    from agent_bitcoin.nwc.service import NWCService

    bus = InMemoryNWCBus()
    if args.mock:
        # Inline minimal fake (mirrors tests)
        class FakeLND:
            def get_info(self):
                return {
                    "alias": "mock",
                    "identity_pubkey": "aa" * 32,
                    "chains": [{"network": "regtest"}],
                    "block_height": 1,
                    "block_hash": "bb" * 32,
                }

            def get_channel_balance(self):
                return SimpleNamespace(local_balance=100_000, remote_balance=0)

            def get_balance(self):
                return SimpleNamespace(confirmed_balance="0")

            def create_invoice(self, memo, amount_sats, expiry_seconds=3600):
                return SimpleNamespace(
                    payment_request=f"lnbcrt_mock_{amount_sats}",
                    payment_hash="cc" * 32,
                    r_hash="cc" * 32,
                )

            def decode_pay_req(self, pr):
                return {"num_satoshis": str(args.amount)}

            def pay_invoice(self, pr, fee_limit_sats=200):
                return SimpleNamespace(
                    success=True, payment_hash="ee" * 32, status="SUCCEEDED"
                )

        lnd = FakeLND()
        print("[smoke] using FakeLND (--mock)")
    else:
        from agent_bitcoin.lightning import LNDClient

        lnd = LNDClient()
        print(f"[smoke] LND_NETWORK={os.getenv('LND_NETWORK', 'regtest')}")

    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=lnd,
        bus=bus,
        budget=NWCBudgetPolicy.from_env(),
        require_enable=True,
    )
    svc.attach()
    uri = svc.issue_connection()
    print(f"[smoke] issued NWC URI (secret redacted, len={len(uri)})")
    print(f"[smoke] wallet_pubkey={svc.wallet_pubkey[:16]}…")

    client = NWCClient(uri, relay=bus, default_timeout=30.0)
    info = client.get_info()
    print(f"[smoke] get_info alias={info.get('alias')} network={info.get('network')}")
    bal = client.get_balance()
    print(f"[smoke] get_balance msats={bal.get('balance')}")

    inv = client.make_invoice(args.amount, description="nwc-regtest-smoke")
    print(f"[smoke] make_invoice amount_msats={inv.get('amount')}")
    print(f"[smoke] invoice={str(inv.get('invoice', ''))[:48]}…")

    if args.pay or args.mock:
        paid = client.pay_invoice(inv["invoice"])
        print(
            f"[smoke] pay_invoice preimage/hash={str(paid.get('preimage', ''))[:16]}…"
        )
    else:
        print("[smoke] skip pay (pass --pay to attempt live payment)")

    print("\nRESULT: PASS — NWC service smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
