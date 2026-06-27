from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
import requests
import time

# === Backend API Client (with fee collection) ===
class AgentBitcoinAPI:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def create_invoice(self, memo: str, amount_sats: int):
        r = requests.post(f"{self.base_url}/invoices", json={"memo": memo, "amount_sats": amount_sats})
        r.raise_for_status()
        return r.json()

    def get_balance(self):
        r = requests.get(f"{self.base_url}/balance")
        r.raise_for_status()
        return r.json()

    def pay_invoice(self, payment_request: str):
        """Pay via backend → triggers 1,000 sat fee automatically"""
        r = requests.post(
            f"{self.base_url}/payments", 
            json={"payment_request": payment_request}
        )
        r.raise_for_status()
        return r.json()

    def check_invoice(self, payment_hash: str):
        r = requests.get(f"{self.base_url}/invoices/{payment_hash}")
        r.raise_for_status()
        return r.json()


api = AgentBitcoinAPI()
llm = ChatOllama(model="llama3.2", temperature=0.3)

prompt = ChatPromptTemplate.from_template(
    """You are an autonomous AI agent that handles Bitcoin Lightning payments.

Current balance: {balance} sats

Decide what action to take based on the goal: {goal}

Respond with one of:
- CREATE_INVOICE:<amount>:<memo>
- CHECK_BALANCE
- DONE

Only respond with the action above."""
)

chain = prompt | llm

def autonomous_agent(goal: str):
    print(f"\n🤖 Autonomous Agent started with goal: {goal}\n")
    
    balance = api.get_balance()["total_sat"]
    print(f"Current balance: {balance} sats")

    response = chain.invoke({"goal": goal, "balance": balance})
    action = response.content.strip()

    print(f"Agent decided: {action}")

    if action.startswith("CREATE_INVOICE"):
        try:
            _, amount, memo = action.split(":", 2)
            amount = int(amount)
            
            invoice = api.create_invoice(memo=memo, amount_sats=amount)
            print(f"\n✅ Invoice created for {amount} sats")
            print(f"Payment Request: {invoice['payment_request'][:80]}...")
            print(f"Payment Hash: {invoice['payment_hash']}")

            print("\n⏳ Paying via Backend API (1,000 sat fee will be collected)...")
            time.sleep(1)
            
            # Pay through backend → fee is automatically collected
            payment_result = api.pay_invoice(invoice['payment_request'])
            print("✅ Payment + Fee Collection Result:", payment_result)

            # Check final status
            status = api.check_invoice(invoice['payment_hash'])
            print(f"Invoice status: {status.get('state', 'unknown')}")

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    autonomous_agent("Create an invoice for 8000 sats and get it paid")