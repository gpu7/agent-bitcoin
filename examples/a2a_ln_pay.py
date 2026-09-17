#!/usr/bin/env python3
"""Agent-to-agent Lightning: two LND nodes, one 100-sat invoice, one pay.

This is NOT the swarm (Alice/Bob sharing one Mac wallet). Two containers:

  Payee: agent-payment-decision-lnd-mainnet  (AWS)
  Payer: agent-bitcoin-lnd-mainnet           (Mac)
         or l402-client-lnd                  (Ubuntu client pack)

Invoice on the payee host; pay on the payer host. Same mainnet latches as L402.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from agent_bitcoin import create_client
from agent_bitcoin.models import Invoice, PaymentResult

DEFAULT_SATS = 100


def _require_latches() -> None:
    net = (os.environ.get("LND_NETWORK") or "").strip().lower()
    if net == "mainnet":
        if os.environ.get("AGENT_BITCOIN_ALLOW_MAINNET") != "1":
            raise SystemExit("Mainnet: set AGENT_BITCOIN_ALLOW_MAINNET=1")
        if os.environ.get("AGENT_BITCOIN_ALLOW_AUTOPAY") != "1":
            raise SystemExit("Mainnet pay: set AGENT_BITCOIN_ALLOW_AUTOPAY=1")


def cmd_invoice(args: argparse.Namespace, client: Any | None = None) -> int:
    if args.offline:
        print("OFFLINE invoice sats=100 payment_request=lnbc1offline…")
        return 0
    _require_latches()
    c = client or create_client()
    inv: Invoice = c.create_invoice(
        memo=args.memo, amount_sats=int(args.sats), expiry_seconds=3600
    )
    bolt = inv.payment_request
    shown = bolt if len(bolt) < 24 else bolt[:16] + "…"
    print(f"invoice sats={args.sats} payment_hash={inv.payment_hash}")
    print(f"payment_request_prefix={shown}")
    print(inv.payment_request)
    print("Pay this BOLT11 on the PAYER node (different LND_CONTAINER).")
    return 0


def cmd_pay(args: argparse.Namespace, client: Any | None = None) -> int:
    bolt11 = (args.bolt11 or "").strip()
    if not bolt11:
        raise SystemExit("--bolt11 is required")
    if args.offline:
        print("OFFLINE pay SUCCEEDED payment_hash=deadbeef preimage=cafef00d")
        return 0
    _require_latches()
    c = client or create_client()
    result: PaymentResult = c.pay_invoice(bolt11)
    print(
        f"pay success={result.success} status={result.status} "
        f"amount={result.amount} payment_hash={result.payment_hash} "
        f"preimage={result.preimage}"
    )
    container = os.environ.get("LND_CONTAINER") or "agent-bitcoin-lnd-mainnet"
    network = os.environ.get("LND_NETWORK") or "mainnet"
    print(
        "Check: docker exec "
        f"{container} lncli --lnddir=/home/lnd/.lnd --network={network} "
        "listpayments --max_payments 3"
    )
    return 0 if result.success else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Two LND nodes: payee invoice, payer pays. Not swarm."
    )
    p.add_argument("--offline", action="store_true", help="No LND (tests)")
    sub = p.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("invoice", help="Create invoice on this node's LND")
    inv.add_argument("--sats", type=int, default=DEFAULT_SATS)
    inv.add_argument("--memo", default="a2a-ln-pay")
    pay = sub.add_parser("pay", help="Pay a BOLT11 with this node's LND")
    pay.add_argument("--bolt11", required=True)
    args = p.parse_args(argv)
    if args.cmd == "invoice":
        return cmd_invoice(args)
    return cmd_pay(args)


if __name__ == "__main__":
    raise SystemExit(main())
