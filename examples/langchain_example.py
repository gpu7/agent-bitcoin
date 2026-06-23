"""
Example: Using Agent-Bitcoin SDK with LangChain
"""

from agent_bitcoin import AgentBitcoinClient, LightningConfig, Lightning
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate


# === 1. Configure your Lightning node (regtest for now) ===
config = LightningConfig(
    host="localhost",
    port=8083,                    # Use Agent-B's port if paying to B, or 8082 for X
    macaroon="PASTE_YOUR_BASE64_MACAROON_HERE",   # From your start script
    network="regtest"
)

lightning = Lightning(config)


# === 2. Define Tools for the Agent ===
@tool
def create_lightning_invoice(amount: int, memo: str = ""):
    """Create a Lightning invoice for receiving payments."""
    result = lightning.create_invoice(amount=amount, memo=memo)
    return {
        "payment_request": result.payment_request,
        "amount": result.amount,
        "memo": result.memo
    }


@tool
def pay_lightning_invoice(payment_request: str):
    """Pay a Lightning invoice."""
    result = lightning.pay_invoice(payment_request=payment_request)
    return {
        "success": result.success,
        "amount": result.amount,
        "payment_hash": result.payment_hash,
        "status": result.status
    }


tools = [create_lightning_invoice, pay_lightning_invoice]


# === 3. Create the Agent ===
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful AI agent that can send and receive Lightning payments."),
    ("placeholder", "{chat_history}"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


# === 4. Test the Agent ===
if __name__ == "__main__":
    response = agent_executor.invoke({
        "input": "Create an invoice for 5000 sats with memo 'Payment for data analysis'."
    })
    print(response)
