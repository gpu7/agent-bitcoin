"""
Simple LangChain + Agent-Bitcoin Example using Ollama
No API key required.
"""

from agent_bitcoin import create_client
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage


# === 1. Initialize SDK ===
client = create_client()


# === 2. Define Tools ===
@tool
def create_lightning_invoice(amount_sats: int, memo: str = "Payment from AI Agent"):
    """Create a Lightning invoice."""
    invoice = client.create_invoice(memo=memo, amount_sats=amount_sats)
    return f"Invoice created for {amount_sats} sats. Payment Request: {invoice.payment_request[:60]}..."


@tool
def pay_lightning_invoice(payment_request: str):
    """Pay a Lightning invoice."""
    result = client.pay_invoice(payment_request=payment_request)
    if result.success:
        return f"✅ Payment successful! Amount: {result.amount} sats | Preimage: {result.preimage}"
    else:
        return f"❌ Payment failed: {result.status}"


@tool
def check_balance():
    """Check Lightning balance."""
    balance = client.get_balance()
    return f"Current balance: {balance.get('total_balance')} sats"


tools = [create_lightning_invoice, pay_lightning_invoice, check_balance]


# === 3. Setup LLM and Test ===
llm = ChatOllama(model="llama3.2", temperature=0)

print("🚀 Testing Agent-Bitcoin with Ollama...\n")

# Simple test
messages = [HumanMessage(content="Create an invoice for 3000 sats with memo 'Test from Ollama'")]

response = llm.bind_tools(tools).invoke(messages)
print("Response:")
print(response.content)

if response.tool_calls:
    print("\nTool calls:", response.tool_calls)