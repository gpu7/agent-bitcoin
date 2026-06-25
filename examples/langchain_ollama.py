"""
Example: Using Agent-Bitcoin SDK with LangChain + Ollama (No API Key Required)
"""

from agent_bitcoin import create_client
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate


# === 1. Initialize the SDK Client ===
client = create_client()


# === 2. Define Tools for the Agent ===
@tool
def create_lightning_invoice(amount_sats: int, memo: str = "Payment from AI Agent"):
    """Create a Lightning invoice for receiving payments."""
    try:
        invoice = client.create_invoice(memo=memo, amount_sats=amount_sats)
        return {
            "success": True,
            "payment_request": invoice.payment_request,
            "amount": amount_sats,
            "memo": memo
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def pay_lightning_invoice(payment_request: str):
    """Pay a Lightning invoice."""
    try:
        result = client.pay_invoice(payment_request=payment_request)
        if result.success:
            return {
                "success": True,
                "amount": result.amount,
                "payment_hash": result.payment_hash,
                "preimage": result.preimage,
                "status": result.status
            }
        else:
            return {
                "success": False,
                "status": result.status,
                "error": "Payment failed"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def check_balance():
    """Check current Lightning balance."""
    try:
        balance = client.get_balance()
        return {
            "total_balance": balance.get("total_balance"),
            "confirmed_balance": balance.get("confirmed_balance")
        }
    except Exception as e:
        return {"error": str(e)}


tools = [create_lightning_invoice, pay_lightning_invoice, check_balance]


# === 3. Create the Agent with Local Ollama ===
llm = ChatOllama(
    model="llama3.2",           # Change to "llama3", "mistral", etc. as needed
    temperature=0,
)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful AI agent that can send and receive Lightning payments on Bitcoin. "
               "Be professional, clear, and accurate when reporting payment status."),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


# === 4. Test the Agent ===
if __name__ == "__main__":
    print("🚀 Starting Lightning Agent with Ollama (Local LLM)...\n")
    print("Make sure Ollama is running with: ollama run llama3.2\n")
    
    response = agent_executor.invoke({
        "input": "Create an invoice for 5000 sats with memo 'Payment for data analysis'."
    })
    
    print("\nFinal Response:")
    print(response["output"])