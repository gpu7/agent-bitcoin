"""Payment decision agents with coded policy limits (not prompt-only)."""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_xai import ChatXAI

from agent_bitcoin.prompts import (
    BITCOIN_LND_SYSTEM_PROMPT,
    PAYMENT_DECISION_DEFAULT_INSTRUCTIONS,
    PAYMENT_DECISION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


class PaymentDecision(Enum):
    PAY = "PAY"
    REJECT = "REJECT"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"


class PaymentDecisionAgent:
    """
    Conservative gatekeeper for Lightning invoice payments.

    Policy is enforced in code first; the LLM only runs if hard limits pass.
    This agent never executes payments — callers must act on the returned decision.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "grok-4-1-fast-reasoning",
        min_sats: Optional[int] = None,
        max_sats: Optional[int] = None,
        confirm_above_sats: Optional[int] = None,
    ):
        self.llm = ChatXAI(
            model=model,
            api_key=api_key,
            temperature=0.1,
        )
        self.system_prompt = PAYMENT_DECISION_SYSTEM_PROMPT
        self.default_instructions = PAYMENT_DECISION_DEFAULT_INSTRUCTIONS

        # Coded limits (env defaults; constructor overrides)
        self.min_sats = (
            min_sats if min_sats is not None else _env_int("MIN_PAYMENT_SATS", 2000)
        )
        self.max_sats = (
            max_sats
            if max_sats is not None
            else _env_int("PAYMENT_DECISION_MAX_SATS", 100_000)
        )
        # Amounts above this require human confirmation (no automatic PAY)
        if confirm_above_sats is not None:
            self.confirm_above_sats = confirm_above_sats
        else:
            raw = os.getenv("PAYMENT_DECISION_CONFIRM_ABOVE_SATS", "").strip()
            self.confirm_above_sats = int(raw) if raw else None

    def _parse_amount(self, invoice_data: dict) -> Optional[int]:
        raw = invoice_data.get("amount_sats")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _policy_gate(self, amount: Optional[int]) -> Optional[dict[str, Any]]:
        """Return a reject/confirm result if policy blocks LLM, else None."""
        if amount is None:
            return {
                "decision": PaymentDecision.REJECT.value,
                "reasoning": "Policy: missing or invalid amount_sats; refusing to evaluate.",
                "blocked_by_policy": True,
                "policy_code": "INVALID_AMOUNT",
                "amount_sats": None,
            }
        if amount < self.min_sats:
            return {
                "decision": PaymentDecision.REJECT.value,
                "reasoning": (
                    f"Policy: amount {amount} sats is below minimum {self.min_sats} sats."
                ),
                "blocked_by_policy": True,
                "policy_code": "BELOW_MINIMUM",
                "amount_sats": amount,
            }
        if amount > self.max_sats:
            return {
                "decision": PaymentDecision.REJECT.value,
                "reasoning": (
                    f"Policy: amount {amount} sats exceeds hard maximum "
                    f"{self.max_sats} sats (PAYMENT_DECISION_MAX_SATS)."
                ),
                "blocked_by_policy": True,
                "policy_code": "ABOVE_MAXIMUM",
                "amount_sats": amount,
            }
        if self.confirm_above_sats is not None and amount > self.confirm_above_sats:
            return {
                "decision": PaymentDecision.CONFIRM_REQUIRED.value,
                "reasoning": (
                    f"Policy: amount {amount} sats is above confirmation threshold "
                    f"{self.confirm_above_sats} sats. Human approval required before PAY."
                ),
                "blocked_by_policy": True,
                "policy_code": "CONFIRM_REQUIRED",
                "amount_sats": amount,
            }
        return None

    def decide_payment(self, invoice_data: dict, context: str = "") -> dict:
        amount = self._parse_amount(invoice_data)
        gate = self._policy_gate(amount)
        if gate is not None:
            result = {
                **gate,
                "raw_response": None,
                "policy": {
                    "min_sats": self.min_sats,
                    "max_sats": self.max_sats,
                    "confirm_above_sats": self.confirm_above_sats,
                },
            }
            logger.info(
                "payment_decision policy_block code=%s decision=%s amount=%s",
                result.get("policy_code"),
                result["decision"],
                amount,
            )
            return result

        # Never put full BOLT11 / secrets in the prompt
        pay_req = str(invoice_data.get("payment_request") or "")
        pay_req_preview = (pay_req[:48] + "…") if len(pay_req) > 48 else pay_req
        memo = str(invoice_data.get("memo") or "No memo")[:200]
        ctx = (context or "No additional context")[:500]

        prompt = f"""Invoice details:
Amount: {amount} sats
Memo: {memo}
Payment Request (truncated): {pay_req_preview or "N/A"}

Context: {ctx}

Hard policy already applied (do not override):
- Minimum: {self.min_sats} sats
- Maximum: {self.max_sats} sats
{f"- Confirm above: {self.confirm_above_sats} sats" if self.confirm_above_sats else ""}

{self.default_instructions}

Should we pay this invoice? Respond with clear reasoning and final decision (PAY / REJECT).
Do not invent payment execution; only decide."""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = self.llm.invoke(messages)
        text = response.content if hasattr(response, "content") else str(response)
        text_upper = text.upper()

        # Prefer explicit REJECT if both words appear
        if "REJECT" in text_upper and "PAY" in text_upper:
            # last occurrence wins lightly: if REJECT after last PAY → reject
            decision = (
                PaymentDecision.REJECT.value
                if text_upper.rfind("REJECT") > text_upper.rfind("PAY")
                else PaymentDecision.PAY.value
            )
        elif "REJECT" in text_upper:
            decision = PaymentDecision.REJECT.value
        elif "PAY" in text_upper:
            decision = PaymentDecision.PAY.value
        else:
            decision = PaymentDecision.REJECT.value  # fail closed

        result = {
            "decision": decision,
            "reasoning": text,
            "raw_response": text,
            "blocked_by_policy": False,
            "policy_code": None,
            "amount_sats": amount,
            "policy": {
                "min_sats": self.min_sats,
                "max_sats": self.max_sats,
                "confirm_above_sats": self.confirm_above_sats,
            },
        }
        logger.info(
            "payment_decision llm decision=%s amount=%s",
            decision,
            amount,
        )
        return result


class BitcoinLNDAgent:
    """Agent for the counterparty node (agent-bitcoin-lnd). Prompt helper only."""

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
        return (
            f"Create a Lightning invoice for {amount_sats} sats "
            f"with memo: '{memo}'. Be professional and clear."
        )


def create_grok_payment_decision_agent(
    api_key: Optional[str] = None,
    **policy_kwargs,
):
    """Create Grok-powered payment decision agent (optional policy kwargs)."""
    return PaymentDecisionAgent(api_key=api_key, **policy_kwargs)


def create_grok_bitcoin_lnd_agent(api_key: Optional[str] = None):
    """Create Grok-powered agent for the counterparty LND node."""
    return BitcoinLNDAgent(api_key=api_key)


# Alias for backward compatibility with __init__.py
create_payment_decision_agent = create_grok_payment_decision_agent
