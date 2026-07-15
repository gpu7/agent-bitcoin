"""Example using Grok-powered payment decision agent."""

from agent_bitcoin import create_client
from agent_bitcoin.agents import create_grok_payment_decision_agent


def main():
    print("🚀 Agent-Bitcoin SDK + Grok Intelligent Agent\n")

    # 1. Initialize Lightning Client
    client = create_client()  # noqa: F841

    # 2. Initialize Grok (xAI)
    # NOTE: You need to set your xAI API key in environment variable: XAI_API_KEY
    decision_agent = create_grok_payment_decision_agent()  # noqa: F841

    print("✅ Grok-powered payment decision agent ready!\n")

    # Example usage (expand as needed)
    print("Use decision_agent.decide_payment(invoice_data) for intelligent decisions.")


if __name__ == "__main__":
    main()
