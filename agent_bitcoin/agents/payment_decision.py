"""
Intelligent Payment Decision Agent
Supports Ollama (local) and xAI Grok.
"""

from typing import Optional, Union
from pydantic import BaseModel
import json

from agent_bitcoin.exceptions import AgentBitcoinError


class PaymentDecision(BaseModel):
    """Structured output from the intelligent payment decision agent."""
    pay: bool
    amount: int
    reason: str
    confidence: float = 0.85
    model_used: str = "unknown"


class PaymentDecisionAgent:
    """
    Intelligent agent that decides whether to approve a Lightning payment.
    Supports multiple LLM backends.
    """

    def __init__(self, llm=None, model: str = "llama3.2"):
        self.llm = llm
        self.model = model

        self.system_prompt = """You are Agent-Payment-Decision, a secure and conservative financial gatekeeper for autonomous AI agents.

STRICT RULES:
- Always respond with valid JSON only.
- Use this exact format:
{
  "pay": true or false,
  "amount": integer in sats,
  "reason": "short, clear explanation"
}
- Approve only if the request is reasonable.
- Reject if amount < 2000, amount > 1_000_000, or looks suspicious.
- Always give a professional reason."""

    def decide(
        self,
        from_agent: str,
        to_agent: str,
        amount_sats: int,
        reason: str = ""
    ) -> PaymentDecision:
        """Make an intelligent payment decision."""

        if self.llm is None:
            return self._rule_based_decision(amount_sats, reason)

        prompt = f"""Payment Request:
From: {from_agent}
To: {to_agent}
Amount: {amount_sats} sats
Reason: {reason or "No reason provided"}

Should this payment be approved?"""

        try:
            response = self.llm.invoke([
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ])

            content = response.content.strip()

            # Clean JSON if wrapped in code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()

            data = json.loads(content)

            return PaymentDecision(
                pay=data.get("pay", False),
                amount=data.get("amount", amount_sats),
                reason=data.get("reason", "Decision by LLM"),
                confidence=0.9,
                model_used=self.model
            )

        except Exception as e:
            return self._rule_based_decision(amount_sats, reason, fallback_reason=str(e))

    def _rule_based_decision(self, amount_sats: int, reason: str = "", fallback_reason: str = "") -> PaymentDecision:
        if amount_sats < 2000:
            return PaymentDecision(
                pay=False,
                amount=amount_sats,
                reason=f"Amount too low ({amount_sats} sats). Minimum is 2000 sats.",
                confidence=0.95,
                model_used="rule-based"
            )
        if amount_sats > 1_000_000:
            return PaymentDecision(
                pay=False,
                amount=amount_sats,
                reason=f"Amount too high ({amount_sats} sats). Maximum is 1,000,000 sats.",
                confidence=0.95,
                model_used="rule-based"
            )

        return PaymentDecision(
            pay=True,
            amount=amount_sats,
            reason=reason or "Approved by rule-based fallback",
            confidence=0.7,
            model_used="rule-based"
        )


# Factory functions
def create_payment_decision_agent(llm=None, model: str = "llama3.2"):
    """Create agent with any LangChain-compatible LLM."""
    return PaymentDecisionAgent(llm=llm, model=model)


def create_grok_payment_decision_agent(api_key: str = None):
    """Create agent using xAI Grok."""
    try:
        from langchain_xai import ChatXAI
        llm = ChatXAI(
            model="grok-4-1-fast-reasoning",   # or grok-beta
            api_key=api_key,
            temperature=0.2,
        )
        return PaymentDecisionAgent(llm=llm, model="grok-4-1")
    except ImportError:
        raise ImportError("langchain-xai is not installed. Run: uv add langchain-xai")