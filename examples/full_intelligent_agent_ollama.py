from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from agent_api_example import AgentBitcoinAPI  # Import the new API client

llm = ChatOllama(model="llama3.2", temperature=0.7)

api = AgentBitcoinAPI()

prompt = ChatPromptTemplate.from_template(
    """You are a helpful AI assistant with Lightning payment capabilities.

Current balance: {balance} sats

User request: {user_input}

If the user wants to send a payment:
1. Decide a reasonable amount (default 5000 sats)
2. Create an invoice using the API
3. Respond with the payment request

Respond naturally."""
)

chain = prompt | llm

def run_agent(user_input: str):
    balance = api.get_balance()["total_sat"]
    
    response = chain.invoke({
        "user_input": user_input,
        "balance": balance
    })
    
    print("Agent:", response.content)
    
    # Optional: Auto-create invoice if needed
    if "pay" in user_input.lower() or "invoice" in user_input.lower():
        invoice = api.create_invoice(
            memo=f"AI Agent Payment - {user_input[:50]}",
            amount_sats=5000
        )
        print("\n✅ Invoice created!")
        print("Payment Request:", invoice["payment_request"])
        print("Payment Hash:", invoice["payment_hash"])

if __name__ == "__main__":
    print("AI Agent with Lightning Backend API (Ollama)")
    while True:
        user = input("\nYou: ")
        if user.lower() in ["exit", "quit"]:
            break
        run_agent(user)