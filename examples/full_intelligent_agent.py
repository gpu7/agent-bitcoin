"""
Full Intelligent Agent Example
============================

End-to-end demonstration of the Agent-Bitcoin SDK with intelligent decision making.
This combines the core client with the PaymentDecisionAgent.
"""

from agent_bitcoin import create_client, create_payment_decision_agent
from langchain_ollama import ChatOllama


def main():
    print("🚀 Agent-Bitcoin Full Intelligent Agent Demo\n")

    # Initialize components
    client = create_client()
    
    # Initialize LLM + Intelligent Decision Agent
    llm = ChatOllama(model="llama3.2", temperature=0.3)
    decision_agent = create_payment_decision_agent(llm=llm)

    print("✅ Lightning Client + Intelligent Decision Agent initialized\n")

    # Test scenarios
    scenarios = [
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 6500,
            "reason": "Payment for completed machine learning training"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 1200,
            "reason": "Small test payment"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 45000,
            "reason": "Monthly service subscription fee"
        },
    ]

    for i, scenario in enumerate(scenarios, 1):
        print(f"\n{'='*90}")
        print(f"SCENARIO {i}: {scenario['amount_sats']} sats")
        print(f"{'='*90}")

        # 1. Intelligent Decision
        decision = decision_agent.decide(
            from_agent=scenario["from_agent"],
            to_agent=scenario["to_agent"],
            amount_sats=scenario["amount_sats"],
            reason=scenario["reason"]
        )

        print(f"Decision : {'✅ APPROVED' if decision.pay else '❌ REJECTED'}")
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
            print("⏭️  Payment skipped due to decision.")

        print()


if __name__ == "__main__":
    main()
