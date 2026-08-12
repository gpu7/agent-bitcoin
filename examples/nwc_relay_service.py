#!/usr/bin/env python3
"""AWS: long-lived NWC wallet listener on public relays (NIP-44).

Prints a nostr+walletconnect URI once, then processes kind 23194 forever
with reconnect backoff. Payments honor existing NWC latches/budgets.

  export AGENT_BITCOIN_NWC_ENABLE=1
  export LND_TRANSPORT=docker
  export LND_CONTAINER=agent-payment-decision-lnd-mainnet  # or regtest name
  # mainnet also needs ALLOW_MAINNET + NWC_ALLOW_MAINNET
  uv run --python 3.12 python examples/nwc_relay_service.py --mock
  # live LND: omit --mock
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from types import SimpleNamespace

from agent_bitcoin.nwc.relays import public_relays_from_env


def _fake_lnd():
    class FakeLND:
        def get_info(self):
            return {
                "alias": "nwc-relay-svc",
                "identity_pubkey": "aa" * 32,
                "chains": [{"network": os.getenv("LND_NETWORK", "regtest")}],
                "block_height": 1,
                "block_hash": "bb" * 32,
            }

        def get_channel_balance(self):
            return SimpleNamespace(local_balance=100_000, remote_balance=0)

        def get_balance(self):
            return SimpleNamespace(confirmed_balance="0")

        def create_invoice(self, memo, amount_sats, expiry_seconds=3600):
            return SimpleNamespace(
                payment_request=f"lnbc_relay_{amount_sats}",
                payment_hash="cc" * 32,
                r_hash="cc" * 32,
            )

        def decode_pay_req(self, pr):
            return {"num_satoshis": "2000"}

        def pay_invoice(self, pr, fee_limit_sats=200):
            return SimpleNamespace(
                success=True, payment_hash="ee" * 32, status="SUCCEEDED"
            )

    return FakeLND()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true")
    p.add_argument("--once", action="store_true", help="print URI and exit (CI)")
    args = p.parse_args()

    try:
        from pynostr.key import PrivateKey
    except ImportError:
        print("uv sync --python 3.12 --extra nostr", file=sys.stderr)
        return 2

    os.environ.setdefault("AGENT_BITCOIN_NWC_ENABLE", "1")
    os.environ.setdefault("LND_TRANSPORT", "docker")

    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.policy import NWCBudgetPolicy
    from agent_bitcoin.nwc.service import NWCService
    from agent_bitcoin.nwc.uri import parse_nwc_uri

    relays = public_relays_from_env()
    lnd = _fake_lnd() if args.mock else None
    if lnd is None:
        from agent_bitcoin.lightning import LNDClient

        lnd = LNDClient()

    bus = InMemoryNWCBus()
    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=lnd,
        bus=bus,
        budget=NWCBudgetPolicy.from_env(),
        require_enable=True,
    )
    svc.attach()
    uri = svc.issue_connection(relays=relays)
    parsed = parse_nwc_uri(uri)
    print("[aws] NWC URI (copy to Mac; do not commit):")
    print(uri)
    print(f"[aws] wallet_pubkey={parsed.wallet_pubkey}")
    print(f"[aws] relays={list(parsed.relays)}")
    print("[aws] encryption=nip44_v2")
    if args.once:
        print("[aws] --once: not listening")
        return 0

    print(
        "[aws] listening (Ctrl+C to stop). Wait for 'subscribed, polling' before Mac."
    )
    # Long-lived: poll public relays for 23194 when not mock
    if args.mock:
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n[aws] stopped")
        return 0

    from agent_bitcoin.nostr.relay import (
        WebsocketNWCRelay,
        run_nwc_listen_session,
    )

    def _log(msg: str) -> None:
        print(f"[aws] {msg}", flush=True)

    def _on_request(d: dict) -> None:
        pk = str(d.get("pubkey") or "")
        print(f"[aws] request from {pk[:16]}…", flush=True)
        svc.handle_request_event(d)
        if bus.all_events():
            last = bus.all_events()[-1]
            if int(last.get("kind") or 0) == 23195:
                ws = WebsocketNWCRelay(relays, timeout=10)
                ws.publish(last)
                print("[aws] published 23195", flush=True)

    backoff = 1.0
    while True:
        try:
            run_nwc_listen_session(
                relays,
                svc.wallet_pubkey,
                _on_request,
                log=_log,
            )
            backoff = 1.0
        except KeyboardInterrupt:
            print("\n[aws] stopped")
            return 0
        except Exception as e:
            print(
                f"[aws] relay error: {e}; reconnect in {backoff:.0f}s", file=sys.stderr
            )
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


if __name__ == "__main__":
    raise SystemExit(main())
