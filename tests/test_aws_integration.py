#!/usr/bin/env python3
"""
Agent-Bitcoin AWS Integration Test with Fee Enforcement
"""

import argparse
import requests
import time

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

        # 3. Pay via AWS backend (with fee enforcement)
        print("💸 Paying invoice via AWS backend (with fee enforcement)...")
        r = requests.post(f"{url}/pay", json={
            "payment_request": invoice['payment_request'],
            "fee_limit_sats": 200
        })
        r.raise_for_status()
        result = r.json()

        if result.get("success"):
            print("✅ Payment + Fee successful!")
            print(f"   Payment Hash: {result.get('payment_hash')}")
            print(f"   Fee Sent: {result.get('fee_sent')} sats to {result.get('fee_address')}")
        else:
            print("❌ Payment failed")
            print(result)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()