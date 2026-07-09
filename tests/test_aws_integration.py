#!/usr/bin/env python3
"""
Agent-Bitcoin AWS Integration Test - Mac pays AWS invoice
"""

import argparse
import requests
import subprocess

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://localhost:8000", help="AWS Backend URL")
    parser.add_argument("--amount", type=int, default=5000, help="Amount in sats")
    args = parser.parse_args()

    url = args.backend_url.rstrip('/')

    print(f"🚀 Testing Agent-Bitcoin AWS Integration at {url}\n")

    try:
        # 1. Check AWS balance
        print("💰 Checking AWS balance...")
        r = requests.get(f"{url}/balance")
        r.raise_for_status()
        data = r.json()
        print(f"AWS Lightning : {data['lightning']['balance']} sats\n")

        # 2. Create invoice on AWS
        print(f"📄 Creating invoice for {args.amount} sats on AWS...")
        r = requests.post(f"{url}/invoices", json={
            "memo": "SDK Integration Test - Mac pays",
            "amount_sats": args.amount
        })
        r.raise_for_status()
        invoice = r.json()
        print("✅ Invoice created!")
        print(f"Payment Request: {invoice['payment_request'][:80]}...\n")

        # 3. Pay from Mac using direct lncli with --force
        print("💸 Paying invoice from Mac node...")
        cmd = [
            "docker", "compose", "-f", "docker-compose.regtest.mac.yml", "exec", "-T", "agent-bitcoin-lnd",
            "lncli", "--lnddir=/home/lnd/.lnd", "--network=regtest", "payinvoice",
            "--fee_limit", "200",
            "--force",   # Skip confirmation prompt
            invoice['payment_request']
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            print("✅ Payment successful!")
            print(result.stdout)
        else:
            print("❌ Payment failed")
            print(result.stderr or result.stdout)

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()