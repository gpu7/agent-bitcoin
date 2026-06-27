from langchain_xai import ChatXAI
from langchain_core.prompts import ChatPromptTemplate
import requests
import time
import subprocess

# === Backend API Client ===
class AgentBitcoinAPI:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url

    def create_invoice(self, memo: str, amount_sats: int):
        r = requests.post(f"{self.base_url}/invoices", json={"memo": memo, "amount_sats": amount_sats})
        return r.json()

    def get_balance(self):
        r = requests.get(f"{self.base_url}/balance")
        return r.json()

    def check_invoice(self, payment_hash: str):
        r = requests.get(f"{self.base_url}/invoices/{payment_hash}")
        return r.json()


api = AgentBitcoinAPI()
llm = ChatXAI(model="grok-3", temperature=0.3)   # or grok-beta / grok-3-mini

prompt = ChatPromptTemplate.from_template(
    """You are an autonomous AI agent managing Lightning Bitcoin payments.

Current balance: {balance} sats

Goal: {goal}

Decide what to do and respond with exactly one of these formats:
- CREATE_INVOICE:<amount>:<memo>
- CHECK_BALANCE
- DONE

Only output the action line."""
)

chain = prompt | llm

def autonomous_grok_agent(goal: str):
    print(f"\n🤖 Grok Autonomous Agent started with goal: {goal}\n")
    
    balance = api.get_balance()["total_sat"]
    print(f"Current balance: {balance} sats")

    response = chain.invoke({"goal": goal, "balance": balance})
    action = response.content.strip()

    print(f"Grok decided: {action}")

    if action.startswith("CREATE_INVOICE"):
        try:
            _, amount, memo = action.split(":", 2)
            amount = int(amount)
            
            invoice = api.create_invoice(memo=memo, amount_sats=amount)
            print(f"\n✅ Invoice created for {amount} sats")
            print(f"Payment Request: {invoice['payment_request'][:80]}...")
            print(f"Payment Hash: {invoice['payment_hash']}")

            # Simulate payment from the other agent (agent-bitcoin-lnd)
            print("\n⏳ Simulating payment from counterparty agent...")
            time.sleep(1)
            
            pay_cmd = [
                "docker", "exec", "agent-bitcoin-lnd", "lncli", "--network=regtest",
                "payinvoice", "--force", f"--pay_req={invoice['payment_request']}"
            ]
            result = subprocess.run(pay_cmd, capture_output=True, text=True)
            print("Payment result:", "SUCCEEDED" if "SUCCEEDED" in result.stdout else "Failed")

            # Check final status
            status = api.check_invoice(invoice['payment_hash'])
            print(f"Invoice status: {status.get('state', 'unknown')}")

        except Exception as e:
            print(f"Error during execution: {e}")


if __name__ == "__main__":
    autonomous_grok_agent("Create an invoice for 12000 sats and get it paid by the other agent")