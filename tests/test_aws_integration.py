#!/usr/bin/env python3
"""
Agent-Bitcoin AWS Integration Test with Fee Enforcement
"""

import argparse
import os
import requests
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backend-url", default="http://localhost:8000", help="AWS Backend URL"
    )
    parser.add_argument("--amount", type=int, default=5000, help="Amount in sats")
    parser.add_argument(
        "--api-key",
        default=os.getenv("AGENT_BITCOIN_API_KEY", ""),
        help="Backend API key (or set AGENT_BITCOIN_API_KEY)",
    )
    args = parser.parse_args()

    url = args.backend_url.rstrip("/")
    api_key = (args.api_key or "").strip()
    if not api_key:
        print(
            "❌ AGENT_BITCOIN_API_KEY / --api-key required for backend /balance, "
            "/invoices, /send-fee"
        )
        return

    headers = {"X-API-Key": api_key}

    print(f"🚀 Testing Agent-Bitcoin AWS Integration at {url}\n")

    try:
        # 1. Check AWS balance
        print("💰 Checking AWS balance...")
        r = requests.get(f"{url}/balance", headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        print(f"AWS Lightning : {data['lightning']['balance']} sats\n")

        # 2. Create invoice on AWS
        print(f"📄 Creating invoice for {args.amount} sats on AWS...")
        r = requests.post(
            f"{url}/invoices",
            json={
                "memo": "SDK Integration Test - Mac pays",
                "amount_sats": args.amount,
            },
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        invoice = r.json()
        print("✅ Invoice created!")
        print(f"Payment Request: {invoice['payment_request']}\n")

        # 3. Pay from Mac node (not from AWS backend)
        print("💸 Paying invoice from Mac LND node...")
        pay_cmd = [
            "docker",
            "compose",
            "-f",
            "docker-compose.regtest.mac.yml",
            "exec",
            "-T",
            "agent-bitcoin-lnd",
            "lncli",
            "--lnddir=/home/lnd/.lnd",
            "--network=regtest",
            "payinvoice",
            "--fee_limit",
            "200",
            "--force",
            invoice["payment_request"],
        ]

        result = subprocess.run(pay_cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ Payment successful from Mac!")
            print(result.stdout)
        else:
            print("❌ Payment failed from Mac")
            print(result.stderr)
            return

        # 4. Send fee to Bitcoin wallet (separate step)
        print("💰 Sending fee to Bitcoin wallet...")
        r = requests.post(f"{url}/send-fee", headers=headers, timeout=120)
        r.raise_for_status()
        fee_result = r.json()
        print(f"✅ Fee sent! TXID: {fee_result.get('txid')}")

        print("\n✅ Full flow completed (Invoice + Payment + Fee enforcement)")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
