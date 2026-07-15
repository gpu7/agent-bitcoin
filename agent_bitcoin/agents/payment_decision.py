from typing import Optional
from langchain_xai import ChatXAI
from langchain_core.messages import SystemMessage, HumanMessage


class PaymentDecisionAgent:
    def __init__(
        self, api_key: Optional[str] = None, model: str = "grok-4-1-fast-reasoning"
    ):
        self.llm = ChatXAI(
            model=model,
            api_key=api_key,
            temperature=0.1,
        )

        # === EDITABLE PROMPT SECTION ===
        self.system_prompt = """You are Agent-Payment-Decision, a secure and conservative financial gatekeeper for autonomous AI agents.

Your job is to evaluate Lightning invoices and decide whether to pay them based on:
- Risk level
- Amount (conservative limits)
- Strategic value
- Available balance

Always prioritize safety and long-term sustainability."""

        self.default_instructions = "Be extremely cautious with large payments. Prefer smaller, frequent payments over large ones."

    def decide_payment(self, invoice_data: dict, context: str = "") -> dict:
        prompt = f"""Invoice details:
Amount: {invoice_data.get("amount_sats", "Unknown")} sats
Memo: {invoice_data.get("memo", "No memo")}
Payment Request: {invoice_data.get("payment_request", "N/A")[:100]}...

Context: {context or "No additional context"}

{self.default_instructions}

Should we pay this invoice? Respond with clear reasoning and final decision (PAY / REJECT)."""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)

        return {
            "decision": "PAY" if "PAY" in response.content.upper() else "REJECT",
            "reasoning": response.content,
            "raw_response": response.content,
        }


def create_grok_payment_decision_agent(api_key: Optional[str] = None):
    """Create Grok-powered payment decision agent."""
    return PaymentDecisionAgent(api_key=api_key)
