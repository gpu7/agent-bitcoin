"""
Example: Using the Intelligent Payment Decision Agent with Ollama
"""

from agent_bitcoin import create_client, create_payment_decision_agent
from langchain_ollama import ChatOllama


def main():
    print("🚀 Intelligent Payment Decision Agent Example\n")

    # 1. Initialize Lightning Client
    lightning_client = create_client()

    # 2. Initialize Ollama LLM
    llm = ChatOllama(
        model="llama3.2",      # You can use "llama3", "mistral", etc.
        temperature=0.3,
    )

    # 3. Create Intelligent Decision Agent
    decision_agent = create_payment_decision_agent(llm=llm)

    # 4. Test Payment Requests
    test_requests = [
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 5000,
            "reason": "Payment for data processing services"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 500,
            "reason": "Small test payment"
        },
        {
            "from_agent": "Agent-X",
            "to_agent": "Agent-Bitcoin",
            "amount_sats": 2500000,
            "reason": "Very large payment"
        },
    ]

    for req in test_requests:
        print(f"\n📋 Request: {req['amount_sats']} sats from {req['from_agent']}")
        decision = decision_agent.decide(
            from_agent=req["from_agent"],
            to_agent=req["to_agent"],
            amount_sats=req["amount_sats"],
            reason=req["reason"]
        )

        status = "✅ APPROVED" if decision.pay else "❌ REJECTED"
        print(f"   {status} | Amount: {decision.amount} sats")
        print(f"   Reason: {decision.reason}")
        print(f"   Confidence: {decision.confidence:.2f}")


if __name__ == "__main__":
    main()