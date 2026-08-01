#!/usr/bin/env python3
"""
Agent-Bitcoin live integration (HTTP backend + optional Mac pay).

Supports regtest and signet via --network / LND_NETWORK.

Examples:
  # Regtest (historical): backend on AWS, pay from Mac peer container
  export AGENT_BITCOIN_API_KEY=...
  uv run python tests/test_aws_integration.py \\
    --network regtest --backend-url http://<AWS_EIP>:8000

  # Signet: backend must use LND_NETWORK=signet (optional fee skip)
  uv run python tests/test_aws_integration.py \\
    --network signet --backend-url http://127.0.0.1:8000 --skip-fee

  # Prefer pure SDK dual-node tests without HTTP:
  #   LND_NETWORK=signet uv run pytest tests/test_lnd_sdk_integration.py -m integration -v
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import requests

from tests.network_config import container_running, stack_for


def _pay_from_peer(network: str, payment_request: str, fee_limit: int) -> int:
    """Pay bolt11 from the stack's payer container via docker exec."""
    stack = stack_for(network)
    container = stack.payer_container
    if not container_running(container):
        print(f"❌ Payer container not running on this host: {container}")
        print("   For dual-node, run the pay step on the host that has the payer LND,")
        print("   or use tests/test_lnd_sdk_integration.py when both are local.")
        return 1

    pay_cmd = [
        "docker",
        "exec",
        "-i",
        container,
        "lncli",
        f"--lnddir={os.getenv('LND_DIR', '/home/lnd/.lnd')}",
        f"--network={network}",
        "sendpayment",
        "--pay_req",
        payment_request,
        "--fee_limit",
        str(fee_limit),
        "--json",
        "--force",
    ]
    print(f"💸 Paying from {container} ({network})...")
    result = subprocess.run(pay_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("✅ Payment successful")
        print(result.stdout)
        return 0
    print("❌ Payment failed")
    print(result.stderr or result.stdout)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live backend integration (regtest or signet)"
    )
    parser.add_argument(
        "--backend-url",
        default=os.getenv("BACKEND_URL", "http://localhost:8000"),
        help="Backend base URL",
    )
    parser.add_argument(
        "--network",
        default=os.getenv("LND_NETWORK", "regtest"),
        choices=["regtest", "signet"],
        help="LND network (default: LND_NETWORK or regtest)",
    )
    parser.add_argument("--amount", type=int, default=2000, help="Amount in sats")
    parser.add_argument(
        "--api-key",
        default=os.getenv("AGENT_BITCOIN_API_KEY", ""),
        help="Backend API key (or set AGENT_BITCOIN_API_KEY)",
    )
    parser.add_argument(
        "--skip-fee",
        action="store_true",
        help="Skip /send-fee (recommended on signet unless fee wallet is funded)",
    )
    parser.add_argument(
        "--skip-pay",
        action="store_true",
        help="Only create invoice via API (no peer pay on this host)",
    )
    parser.add_argument("--fee-limit", type=int, default=500)
    args = parser.parse_args()

    url = args.backend_url.rstrip("/")
    api_key = (args.api_key or "").strip()
    if not api_key:
        print(
            "❌ AGENT_BITCOIN_API_KEY / --api-key required for backend "
            "/balance, /invoices, /send-fee"
        )
        return 1

    network = args.network.strip().lower()
    stack = stack_for(network)
    headers = {"X-API-Key": api_key}

    print(f"🚀 Integration at {url}  network={network}")
    print(f"   agent={stack.agent_container}  peer={stack.peer_container}")
    print(
        f"   dual roles: receiver={stack.receiver_container} payer={stack.payer_container}\n"
    )

    try:
        print("💰 Checking balance...")
        r = requests.get(f"{url}/balance", headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        ln = data.get("lightning") or {}
        bal = ln.get("balance", ln.get("local_balance", "?"))
        print(f"Lightning balance field: {bal}\n")

        print(f"📄 Creating invoice for {args.amount} sats via API...")
        r = requests.post(
            f"{url}/invoices",
            json={
                "memo": f"SDK Integration Test ({network})",
                "amount_sats": args.amount,
            },
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        invoice = r.json()
        pr = invoice.get("payment_request") or ""
        print("✅ Invoice created")
        print(
            f"Payment Request: {pr[:48]}…\n"
            if len(pr) > 48
            else f"Payment Request: {pr}\n"
        )

        if not args.skip_pay:
            # Backend creates invoice on agent node → peer (payer) pays it.
            # Signet stack defaults: agent is AWS (receiver for this HTTP path),
            # Mac pays if local — override by running pay only where payer lives.
            rc = _pay_from_peer(network, pr, args.fee_limit)
            if rc != 0:
                return rc
        else:
            print("⏭  --skip-pay: not paying on this host")

        if not args.skip_fee:
            print("💰 Sending fee via /send-fee...")
            r = requests.post(f"{url}/send-fee", headers=headers, timeout=120)
            r.raise_for_status()
            fee_result = r.json()
            print(f"✅ Fee sent! TXID: {fee_result.get('txid')}")
        else:
            print("⏭  --skip-fee")

        print("\n✅ Integration flow finished")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
