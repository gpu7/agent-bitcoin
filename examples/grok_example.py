"""
Example: Using Agent-Bitcoin Intelligent Agent with xAI Grok
"""

from agent_bitcoin import create_client, create_grok_payment_decision_agent
from langchain_xai import ChatXAI


def main():
    print("🚀 Agent-Bitcoin SDK + xAI Grok Intelligent Agent\n")

    # 1. Initialize Lightning Client
    client = create_client()

    # 2. Initialize Grok (xAI)
    # NOTE: You need to set your xAI API key in environment variable: XAI_API_KEY
    llm = ChatXAI(
        model="grok-4-1-fast-reasoning",   # or "grok-beta"
        temperature=0.2,
    )

    # 3. Create Intelligent Decision Agent with Grok
    decision_agent = create_grok_payment_decision_agent()

    print("✅ Client and Grok Decision Agent initialized\n")

    # Test cases
    test_cases = [
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 6500,
            "reason": "Payment for machine learning model training"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 1200,
            "reason": "Small test transfer"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 2500000,
            "reason": "Large strategic payment"
        },
    ]

    for case in test_cases:
        print(f"\n📋 Request: {case['amount_sats']} sats from {case['from_agent']}")
        
        decision = decision_agent.decide(
            from_agent=case["from_agent"],
            to_agent=case["to_agent"],
            amount_sats=case["amount_sats"],
            reason=case["reason"]
        )

        status = "✅ APPROVED" if decision.pay else "❌ REJECTED"
        print(f"   {status}")
        print(f"   Amount : {decision.amount} sats")
        print(f"   Reason : {decision.reason}")
        print(f"   Model  : {decision.model_used}")
        print(f"   Confidence: {decision.confidence:.2f}")
        print("-" * 70)


if __name__ == "__main__":
    main()
