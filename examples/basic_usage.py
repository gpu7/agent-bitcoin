"""
Basic Usage + Intelligent Payment Decision Agent
"""

from agent_bitcoin import create_client, create_payment_decision_agent
from langchain_ollama import ChatOllama


def main():
    print("🚀 Agent-Bitcoin SDK + Intelligent Agent\n")

    # Initialize core Lightning client
    client = create_client()

    # Initialize Intelligent Decision Agent with Ollama
    llm = ChatOllama(model="llama3.2", temperature=0.3)
    decision_agent = create_payment_decision_agent(llm=llm)

    print("✅ Lightning Client and Intelligent Agent ready\n")

    # Test cases
    test_cases = [
        ("Agent-X", "Agent-Bitcoin", 4500, "Payment for completed analysis"),
        ("Agent-X", "Agent-Bitcoin", 800, "Small test payment"),
        ("Agent-X", "Agent-Bitcoin", 1500000, "Large transfer"),
    ]

    for from_agent, to_agent, amount, reason in test_cases:
        print(f"📋 Request → {amount} sats | Reason: {reason}")
        
        decision = decision_agent.decide(
            from_agent=from_agent,
            to_agent=to_agent,
            amount_sats=amount,
            reason=reason
        )

        status = "✅ APPROVED" if decision.pay else "❌ REJECTED"
        print(f"   {status} | Amount: {decision.amount} sats")
        print(f"   Reason: {decision.reason}")
        print(f"   Confidence: {decision.confidence:.2f} | Model: {decision.model_used}")
        print("-" * 70)


if __name__ == "__main__":
    main()