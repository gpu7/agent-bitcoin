"""
Intelligent Payment Decision Agent
----------------------------------
Similar to your n8n "Agent-Payment-Decision" node.
Supports Ollama (local) and xAI Grok.
"""

from typing import Optional
from pydantic import BaseModel
import json


class PaymentDecision(BaseModel):
    """Structured output from the intelligent payment decision agent."""
    pay: bool
    amount: int
    reason: str
    confidence: float = 0.85


class PaymentDecisionAgent:
    """
    Intelligent agent that decides whether to approve a Lightning payment.
    Uses LLM for reasoning when available.
    """

    def __init__(self, llm=None, model: str = "llama3.2"):
        """
        Args:
            llm: LangChain LLM instance (ChatOllama, ChatXAI, etc.)
            model: Model name to use if llm is not provided
        """
        self.llm = llm
        self.model = model

        self.system_prompt = """You are Agent-Payment-Decision, a secure and conservative financial gatekeeper for AI agents.

STRICT RULES:
- Always respond with **valid JSON only**.
- Use this exact format:
{
  "pay": true or false,
  "amount": integer (in sats),
  "reason": "short clear explanation"
}
- Approve only if the request is reasonable.
- Reject if amount is too low (< 2000), too high (> 1,000,000), or looks suspicious.
- Always give a short, professional reason."""

    def decide(
        self,
        from_agent: str,
        to_agent: str,
        amount_sats: int,
        reason: str = ""
    ) -> PaymentDecision:
        """Make an intelligent payment decision."""

        # Fallback if no LLM is configured
        if self.llm is None:
            return self._rule_based_decision(amount_sats, reason)

        prompt = f"""Payment Request:
- From: {from_agent}
- To: {to_agent}
- Amount: {amount_sats} sats
- Reason: {reason or "No reason provided"}

Should this payment be approved?"""

        try:
            # Call the LLM
            response = self.llm.invoke([
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ])

            # Try to parse JSON from the response
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].strip()

            decision_data = json.loads(content)
            return PaymentDecision(
                pay=decision_data.get("pay", False),
                amount=decision_data.get("amount", amount_sats),
                reason=decision_data.get("reason", "Decision made by LLM"),
                confidence=0.9
            )

        except Exception as e:
            # Fallback to rule-based on any error
            return self._rule_based_decision(amount_sats, reason, fallback_reason=str(e))

    def _rule_based_decision(
        self, amount_sats: int, reason: str = "", fallback_reason: str = ""
    ) -> PaymentDecision:
        """Simple rule-based fallback."""
        if amount_sats < 2000:
            return PaymentDecision(
                pay=False,
                amount=amount_sats,
                reason=f"Amount too low ({amount_sats} sats). Minimum is 2000 sats.",
                confidence=0.95
            )
        if amount_sats > 1_000_000:
            return PaymentDecision(
                pay=False,
                amount=amount_sats,
                reason=f"Amount too high ({amount_sats} sats). Maximum is 1,000,000 sats.",
                confidence=0.95
            )
        return PaymentDecision(
            pay=True,
            amount=amount_sats,
            reason=reason or "Approved by rule-based system",
            confidence=0.7
        )


def create_payment_decision_agent(llm=None, model: str = "llama3.2"):
    """Factory function to create a PaymentDecisionAgent."""
    return PaymentDecisionAgent(llm=llm, model=model)