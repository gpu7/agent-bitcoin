"""
Simple & Reliable Example: Agent-Bitcoin SDK + Ollama
No complex agent framework — just direct tool usage.
"""

from agent_bitcoin import create_client
from langchain_core.tools import tool
from langchain_ollama import ChatOllama


# === 1. Initialize SDK ===
client = create_client()


# === 2. Define Tools ===
@tool
def create_lightning_invoice(amount_sats: int, memo: str = "Payment from AI Agent"):
    """Create a Lightning invoice."""
    invoice = client.create_invoice(memo=memo, amount_sats=amount_sats)
    return f"✅ Invoice created!\nAmount: {amount_sats} sats\nMemo: {memo}\nPayment Request: {invoice.payment_request[:80]}..." 


@tool
def pay_lightning_invoice(payment_request: str):
    """Pay a Lightning invoice."""
    result = client.pay_invoice(payment_request=payment_request)
    if result.success:
        return f"✅ Payment Successful!\nAmount: {result.amount} sats\nHash: {result.payment_hash}\nPreimage: {result.preimage}"
    else:
        return f"❌ Payment Failed: {result.status}"


@tool
def check_balance():
    """Check Lightning balance."""
    balance = client.get_balance()
    return f"Current Balance: {balance.get('total_balance')} sats (Confirmed: {balance.get('confirmed_balance')} sats)"


tools = [create_lightning_invoice, pay_lightning_invoice, check_balance]


# === 3. Setup Local LLM ===
llm = ChatOllama(model="llama3.2", temperature=0)


# === 4. Test Tools Directly ===
if __name__ == "__main__":
    print("🚀 Agent-Bitcoin SDK + Ollama Example\n")
    
    # Test 1: Create Invoice
    print("🟡 Creating invoice for 5000 sats...")
    result1 = create_lightning_invoice.invoke({"amount_sats": 5000, "memo": "Test from Ollama"})
    print(result1)
    
    print("\n" + "="*60)
    
    # Test 2: Check Balance
    print("🟡 Checking balance...")
    result2 = check_balance.invoke({})
    print(result2)
    
    print("\n✅ Example completed successfully!")
    print("You can now expand this into a full agent if desired.")