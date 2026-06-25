"""
Basic Usage + Intelligent Agent Example
"""

from agent_bitcoin import create_client, create_payment_decision_agent
from langchain_ollama import ChatOllama


def main():
    print("🚀 Agent-Bitcoin SDK - Basic + Intelligent Agent Example\n")

    # Initialize Lightning Client
    client = create_client()

    # Initialize Intelligent Decision Agent with Ollama
    llm = ChatOllama(model="llama3.2", temperature=0.3)
    decision_agent = create_payment_decision_agent(llm=llm)

    print("✅ Client and Intelligent Agent initialized\n")

    # Test payment request
    request = {
        "from_agent": "Agent-X",
        "to_agent": "Agent-Bitcoin",
        "amount_sats": 4500,
        "reason": "Payment for completed data analysis task"
    }

    print(f"📋 Payment Request: {request['amount_sats']} sats from {request['from_agent']}")
    
    decision = decision_agent.decide(
        from_agent=request["from_agent"],
        to_agent=request["to_agent"],
        amount_sats=request["amount_sats"],
        reason=request["reason"]
    )

    status = "✅ APPROVED" if decision.pay else "❌ REJECTED"
    print(f"\n{status}")
    print(f"Amount: {decision.amount} sats")
    print(f"Reason: {decision.reason}")
    print(f"Confidence: {decision.confidence:.2f}")
    print(f"Model: {decision.model_used}")

    if decision.pay:
        print("\n💸 Proceeding to create invoice and pay...")
        # You can add actual payment logic here later


if __name__ == "__main__":
    main()