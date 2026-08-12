#!/usr/bin/env python3
"""N6 mainnet NWC smoke — tight budget (default 2000 sats), multi-latch.

Requires explicit operator go via env (all required):

  export LND_NETWORK=mainnet
  export AGENT_BITCOIN_ALLOW_MAINNET=1
  export AGENT_BITCOIN_NWC_ENABLE=1
  export AGENT_BITCOIN_NWC_ALLOW_MAINNET=1
  export LND_TRANSPORT=docker
  export LND_CONTAINER=agent-payment-decision-lnd-mainnet   # AWS invoice/service
  # optional tighter overrides:
  # export NWC_MAX_PAYMENT_SATS=2000
  # export NWC_MIN_PAYMENT_SATS=2000

  uv sync --python 3.12 --extra nostr --group dev
  uv run --python 3.12 python examples/nwc_mainnet_smoke.py --amount 2000

Same-process in-memory bus (lab transport). LND must be unlocked.
Default is invoice-only; pass --pay only after confirming channel liquidity.

Hard stop after one successful session:
  unset AGENT_BITCOIN_NWC_ALLOW_MAINNET AGENT_BITCOIN_NWC_ENABLE AGENT_BITCOIN_ALLOW_MAINNET
"""

from __future__ import annotations

import argparse
import os
import sys


def _require_mainnet_latches() -> None:
    missing = []
    if os.getenv("LND_NETWORK", "").strip().lower() != "mainnet":
        missing.append("LND_NETWORK=mainnet")
    if os.getenv("AGENT_BITCOIN_ALLOW_MAINNET", "").strip() != "1":
        missing.append("AGENT_BITCOIN_ALLOW_MAINNET=1")
    if os.getenv("AGENT_BITCOIN_NWC_ENABLE", "").strip() not in {
        "1",
        "true",
        "TRUE",
    }:
        missing.append("AGENT_BITCOIN_NWC_ENABLE=1")
    if os.getenv("AGENT_BITCOIN_NWC_ALLOW_MAINNET", "").strip() not in {
        "1",
        "true",
        "TRUE",
    }:
        missing.append("AGENT_BITCOIN_NWC_ALLOW_MAINNET=1")
    if missing:
        print(
            "Refusing mainnet NWC smoke — set all of:\n  " + "\n  ".join(missing),
            file=sys.stderr,
        )
        print(
            "See docs/nwc-automatic-wallets.md (N6) for the tight-budget go.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def main() -> int:
    p = argparse.ArgumentParser(description="Mainnet NWC tight-budget smoke (N6)")
    p.add_argument(
        "--amount",
        type=int,
        default=2000,
        help="sats (default 2000; must be within NWC mainnet max)",
    )
    p.add_argument(
        "--pay",
        action="store_true",
        help="Also pay the invoice (needs local LN outbound)",
    )
    p.add_argument(
        "--memo",
        default="nwc-mainnet-n6-smoke",
        help="Invoice memo",
    )
    p.add_argument(
        "--yes-mainnet",
        action="store_true",
        help="Acknowledge real sats (required)",
    )
    args = p.parse_args()

    if not args.yes_mainnet:
        print(
            "Pass --yes-mainnet to acknowledge real mainnet funds movement.",
            file=sys.stderr,
        )
        return 2

    _require_mainnet_latches()

    try:
        from pynostr.key import PrivateKey
    except ImportError:
        print("uv sync --python 3.12 --extra nostr", file=sys.stderr)
        return 2

    os.environ.setdefault("LND_TRANSPORT", "docker")

    from agent_bitcoin.lightning import LNDClient
    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import NWCClient
    from agent_bitcoin.nwc.flow import nwc_pay_if_approved, rule_based_decision
    from agent_bitcoin.nwc.policy import NWCBudgetPolicy, assert_nwc_network_allowed
    from agent_bitcoin.nwc.service import NWCService

    assert_nwc_network_allowed()
    budget = NWCBudgetPolicy.from_env()
    print(
        f"[n6] network=mainnet budget min={budget.min_sats} max={budget.max_sats} "
        f"amount={args.amount}"
    )
    if args.amount > budget.max_sats:
        print(
            f"amount {args.amount} exceeds NWC mainnet max {budget.max_sats}",
            file=sys.stderr,
        )
        return 2

    bus = InMemoryNWCBus()
    lnd = LNDClient()
    print(f"[n6] LND container={getattr(lnd, 'container', '?')}")

    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=lnd,
        bus=bus,
        budget=budget,
        require_enable=True,
        fee_limit_sats=int(os.getenv("NWC_FEE_LIMIT_SATS", "50")),
    )
    svc.attach()
    uri = svc.issue_connection()
    client = NWCClient(uri, relay=bus, default_timeout=60.0)

    info = client.get_info()
    print(f"[n6] get_info alias={info.get('alias')} network={info.get('network')}")
    bal = client.get_balance()
    print(f"[n6] get_balance msats={bal.get('balance')}")

    decision = rule_based_decision(
        args.amount,
        min_sats=budget.min_sats,
        max_sats=budget.max_sats,
        context=args.memo,
    )
    print(f"[n6] decision => {decision}")
    if not decision.get("pay"):
        print("[n6] STOP: not PAY")
        return 0

    inv = client.make_invoice(args.amount, description=args.memo)
    bolt11 = str(inv.get("invoice") or "")
    print(f"[n6] make_invoice ok len={len(bolt11)} hash={inv.get('payment_hash')}")

    if not args.pay:
        print("[n6] invoice only (re-run with --pay to settle via NWC on this node)")
        print("\nRESULT: PASS — mainnet NWC invoice path")
        return 0

    paid = nwc_pay_if_approved(client, decision, bolt11, amount_sats=args.amount)
    print(f"[n6] pay result => {paid}")
    print("\nRESULT: PASS — mainnet NWC pay (unset latches after session)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
