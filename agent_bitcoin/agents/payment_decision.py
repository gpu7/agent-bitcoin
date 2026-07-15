from typing import Optional
from langchain_xai import ChatXAI
from langchain_core.messages import SystemMessage, HumanMessage

from agent_bitcoin.prompts import (
    PAYMENT_DECISION_SYSTEM_PROMPT,
    PAYMENT_DECISION_DEFAULT_INSTRUCTIONS,
    BITCOIN_LND_SYSTEM_PROMPT,
)


class PaymentDecisionAgent:
    """Agent for deciding whether to pay Lightning invoices (conservative gatekeeper)."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "grok-4-1-fast-reasoning"
    ):
        self.llm = ChatXAI(
            model=model,
            api_key=api_key,
            temperature=0.1,
        )
        self.system_prompt = PAYMENT_DECISION_SYSTEM_PROMPT
        self.default_instructions = PAYMENT_DECISION_DEFAULT_INSTRUCTIONS

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


class BitcoinLNDAgent:
    """Agent for the counterparty node (agent-bitcoin-lnd)."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "grok-4-1-fast-reasoning"
    ):
        self.llm = ChatXAI(
            model=model,
            api_key=api_key,
            temperature=0.3,
        )
        self.system_prompt = BITCOIN_LND_SYSTEM_PROMPT

    def create_invoice_prompt(self, amount_sats: int, memo: str) -> str:
        return f"Create a Lightning invoice for {amount_sats} sats with memo: '{memo}'. Be professional and clear."


def create_grok_payment_decision_agent(api_key: Optional[str] = None):
    """Create Grok-powered payment decision agent."""
    return PaymentDecisionAgent(api_key=api_key)


def create_grok_bitcoin_lnd_agent(api_key: Optional[str] = None):
    """Create Grok-powered agent for the counterparty LND node."""
    return BitcoinLNDAgent(api_key=api_key)
