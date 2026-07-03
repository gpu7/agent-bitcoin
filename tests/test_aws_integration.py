#!/usr/bin/env python3
"""
Test case for Agent-Bitcoin SDK with remote AWS Backend API
"""

import argparse
from agent_bitcoin import create_client, LightningConfig


def main():
    parser = argparse.ArgumentParser(description="Test Agent-Bitcoin SDK with AWS Backend")
    parser.add_argument("--backend-url", default="http://localhost:8000",
                        help="Backend URL (default: http://localhost:8000)")
    parser.add_argument("--amount", type=int, default=5000,
                        help="Invoice amount in sats (default: 5000)")
    args = parser.parse_args()

    print(f"🚀 Testing Agent-Bitcoin SDK with Backend: {args.backend_url}\n")

    # Create client with custom backend URL
    client = create_client(backend_url=args.backend_url)

    try:
        # Test 1: Get balances
        print("💰 Checking balances...")
        balance = client.get_balance()
        print(f"Lightning: {balance.lightning.balance} sats")
        print(f"On-chain: {balance.onchain.total_balance} sats")

        # Test 2: Create invoice
        print(f"\n📄 Creating invoice for {args.amount} sats...")
        invoice = client.create_invoice(
            memo=f"AWS Test - {args.amount} sats",
            amount_sats=args.amount
        )
        print("✅ Invoice created!")
        print(f"   Payment Request: {invoice.payment_request[:80]}...")

        # Test 3: Pay the invoice
        print("\n💸 Paying invoice...")
        result = client.pay_invoice(
            payment_request=invoice.payment_request,
            fee_limit_sats=300
        )

        if result.success:
            print("✅ Payment successful!")
            print(f"   Amount paid: {result.amount} sats")
            print(f"   Payment Hash: {result.payment_hash}")
            print(f"   Preimage: {result.preimage}")
        else:
            print("❌ Payment failed")
            print(f"   Status: {result.status}")
            print(f"   Reason: {result.raw_response}")

        # Test 4: Check updated balance
        print("\n💰 Checking updated balances...")
        updated = client.get_balance()
        print(f"Lightning: {updated.lightning.balance} sats")

    except Exception as e:
        print(f"❌ Error during test: {e}")


if __name__ == "__main__":
    main()