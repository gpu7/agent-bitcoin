#!/usr/bin/env python3
"""
Test case for Agent-Bitcoin SDK with AWS Backend API (regtest)
"""

import time
from agent_bitcoin import create_client


def test_aws_integration():
    print("🚀 Testing Agent-Bitcoin SDK with AWS Backend API...\n")

    # Create client (points to your AWS backend on localhost:8000)
    client = create_client()

    try:
        # Test 1: Get balances
        print("💰 Checking balances...")
        balance = client.get_balance()
        print(f"Lightning: {balance.lightning.balance} sats")
        print(f"On-chain: {balance.onchain.total_balance} sats")

        # Test 2: Create invoice on Agent-Bitcoin (via AWS backend)
        print("\n📄 Creating invoice...")
        invoice = client.create_invoice(
            memo="AWS Integration Test - 5000 sats",
            amount_sats=5000
        )
        print("✅ Invoice created!")
        print(f"   Payment Request: {invoice.payment_request[:80]}...")

        # Test 3: Pay the invoice (from payment-decision node via backend)
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
    test_aws_integration()
