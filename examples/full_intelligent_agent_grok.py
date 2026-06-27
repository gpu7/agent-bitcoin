from langchain_xai import ChatXAI
from langchain_core.prompts import ChatPromptTemplate
from agent_api_example import AgentBitcoinAPI

llm = ChatXAI(model="grok-3", temperature=0.7)

api = AgentBitcoinAPI()

prompt = ChatPromptTemplate.from_template(
    """You are a helpful AI assistant with Lightning Bitcoin payment capabilities.

Current balance: {balance} sats

User request: {user_input}

If the user asks to send money or create a payment, create an invoice and show the payment request.

Respond naturally and helpfully."""
)

chain = prompt | llm

def run_agent(user_input: str):
    balance = api.get_balance()["total_sat"]
    
    response = chain.invoke({
        "user_input": user_input,
        "balance": balance
    })
    
    print("Grok Agent:", response.content)
    
    if any(word in user_input.lower() for word in ["pay", "send", "invoice", "bitcoin", "sats"]):
        invoice = api.create_invoice(
            memo=f"Grok Agent Payment - {user_input[:50]}",
            amount_sats=5000
        )
        print("\n✅ Invoice created via Backend API!")
        print("Payment Request:", invoice["payment_request"])
        print("Payment Hash:", invoice["payment_hash"])

if __name__ == "__main__":
    print("Grok AI Agent with Lightning Backend API")
    while True:
        user = input("\nYou: ")
        if user.lower() in ["exit", "quit"]:
            break
        run_agent(user)