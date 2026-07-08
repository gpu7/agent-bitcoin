#!/usr/bin/env python3
"""
Agent-Bitcoin AWS Integration Test - Full Workflow
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
        # 1. Check balance
        print("💰 Checking balance...")
        r = requests.get(f"{url}/balance")
        r.raise_for_status()
        data = r.json()
        print(f"Lightning : {data['lightning']['balance']} sats")
        print(f"On-chain  : {data['onchain']['total_balance']} sats\n")

        # 2. Create invoice on AWS backend
        print(f"📄 Creating invoice for {args.amount} sats...")
        r = requests.post(f"{url}/invoices", json={
            "memo": "SDK Integration Test",
            "amount_sats": args.amount
        })
        r.raise_for_status()
        invoice = r.json()
        print("✅ Invoice created!")
        print(f"Payment Request: {invoice['payment_request'][:80]}...\n")

        # 3. Pay the invoice (using SDK or direct call)
        print("💸 Paying invoice from Mac node...")
        # For now, assume backend has a /pay endpoint or use SDK later
        r = requests.post(f"{url}/pay", json={
            "payment_request": invoice['payment_request'],
            "fee_limit_sats": 200
        })
        r.raise_for_status()
        result = r.json()

        if result.get("success"):
            print("✅ Payment successful!")
            print(f"Amount: {result.get('amount')} sats")
            print(f"Payment Hash: {result.get('payment_hash')}")
        else:
            print("❌ Payment failed")
            print(result)

    except requests.exceptions.RequestException as e:
        print(f"❌ API Error: {e}")
        if hasattr(e.response, 'text'):
            print(e.response.text)
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()