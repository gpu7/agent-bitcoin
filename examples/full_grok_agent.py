"""
Full Intelligent Agent Example using xAI Grok
===========================================

End-to-end demonstration using Grok for intelligent payment decisions.
"""

from agent_bitcoin import create_client, create_grok_payment_decision_agent
from langchain_xai import ChatXAI


def main():
    print("🚀 Agent-Bitcoin Full Intelligent Agent with xAI Grok\n")

    # Initialize Lightning Client
    client = create_client()

    # Initialize Grok + Intelligent Decision Agent
    decision_agent = create_grok_payment_decision_agent()

    print("✅ Lightning Client + Grok Decision Agent initialized\n")
    print("Note: Using xAI Grok model for decision making.\n")

    # Test scenarios
    scenarios = [
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 7200,
            "reason": "Payment for advanced AI model training services"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 900,
            "reason": "Small experimental transfer"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 85000,
            "reason": "Quarterly infrastructure subscription"
        },
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'='*90}")
        print(f"SCENARIO {i}: {scenario['amount_sats']} sats")
        print(f"{'='*90}")

        # 1. Intelligent Decision using Grok
        decision = decision_agent.decide(
            from_agent=scenario["from_agent"],
            to_agent=scenario["to_agent"],
            amount_sats=scenario["amount_sats"],
            reason=scenario["reason"]
        )

        status = "✅ APPROVED" if decision.pay else "❌ REJECTED"
        print(f"Decision : {status}")
        print(f"Reason   : {decision.reason}")
        print(f"Confidence: {decision.confidence:.1%} | Model: {decision.model_used}\n")

        if decision.pay:
            # 2. Create Invoice
            print("📄 Creating Lightning Invoice...")
            invoice = client.create_invoice(
                memo=scenario["reason"],
                amount_sats=decision.amount
            )
            print(f"   → Invoice created for {decision.amount} sats")

            # 3. Execute Payment
            print("💸 Executing Lightning Payment...")
            result = client.pay_invoice(invoice.payment_request)

            if result.success:
                print("✅ PAYMENT SUCCESSFUL")
                print(f"   Amount     : {result.amount} sats")
                print(f"   Hash       : {result.payment_hash}")
                print(f"   Preimage   : {result.preimage}")
            else:
                print(f"❌ Payment Failed: {result.status}")
        else:
            print("⏭️  Payment skipped due to intelligent decision.")

        print()


if __name__ == "__main__":
    main()
