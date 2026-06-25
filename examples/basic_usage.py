"""
Basic Usage Example for Agent-Bitcoin SDK
=======================================

Simple, straightforward examples showing core functionality.
No LangChain or complex dependencies required.
"""

from agent_bitcoin import create_client


def main():
    print("🚀 Agent-Bitcoin SDK - Basic Usage Example\n")

    # Initialize client (loads configuration from .env automatically)
    client = create_client()

    print("✅ Client initialized successfully\n")

    # 1. Create a Lightning Invoice
    print("📄 1. Creating Lightning Invoice...")
    invoice = client.create_invoice(
        memo="Test payment from basic example",
        amount_sats=5000
    )
    print(f"   Amount: 5000 sats")
    print(f"   Memo: 'Test payment from basic example'")
    print(f"   Payment Request: {invoice.payment_request[:60]}...\n")

    # 2. Get Balance
    print("💰 2. Checking Lightning Balance...")
    balance = client.get_balance()
    print(f"   Total Balance: {balance.get('total_balance')} sats")
    print(f"   Confirmed: {balance.get('confirmed_balance')} sats\n")

    # 3. Pay an Invoice (uncomment when you have a real payment_request)
    # print("💸 3. Paying Lightning Invoice...")
    # result = client.pay_invoice(invoice.payment_request)
    # 
    # if result.success:
    #     print(f"✅ Payment Successful!")
    #     print(f"   Amount: {result.amount} sats")
    #     print(f"   Payment Hash: {result.payment_hash}")
    #     print(f"   Preimage: {result.preimage}")
    # else:
    #     print(f"❌ Payment Failed: {result.status}")

    print("🎉 Basic examples completed!")
    print("\nNext steps:")
    print("   • Try the LangChain example: examples/ollama_example.py")
    print("   • Explore more methods with: dir(client)")


if __name__ == "__main__":
    main()
