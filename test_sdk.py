#!/usr/bin/env python3
"""
Quick test for the Agent-Bitcoin SDK
"""

from agent_bitcoin import create_client


def main():
    print("🚀 Testing Agent-Bitcoin SDK...\n")

    # Option 1: Using convenience function
    client = create_client()

    # Option 2: Manual config (uncomment if you want to customize)
    # from agent_bitcoin import LightningConfig
    # config = LightningConfig(
    #     container_payment_decision="agent-payment-decision-lnd",
    #     container_bitcoin="agent-bitcoin-lnd"
    # )
    # client = AgentBitcoinClient(config)

    try:
        # Test 1: Create an invoice on Agent-Bitcoin
        print("📄 Creating invoice...")
        invoice = client.create_invoice(
            memo="SDK Test Payment - 1000 sats", amount_sats=1000
        )
        print("✅ Invoice created!")
        print(f"   Payment Request: {invoice.payment_request[:80]}...")

        # Test 2: Pay the invoice from Agent-Payment-Decision
        print("\n💸 Paying invoice...")
        result = client.pay_invoice(
            payment_request=invoice.payment_request, fee_limit_sats=200
        )

        if result.success:
            print("✅ Payment successful!")
            print(f"   Amount: {result.amount} sats")
            print(f"   Payment Hash: {result.payment_hash}")
            print(f"   Preimage: {result.preimage}")
        else:
            print("❌ Payment failed")
            print(f"   Status: {result.status}")
            print(f"   Reason: {result.raw_response}")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
