"""
ABT agent policy — coded limits for PaymentDecisionAgent (no live LLM).

Aligned with shared DEFAULT_MIN_PAYMENT_SATS / DEFAULT_MAX_PAYMENT_SATS.
"""

from unittest.mock import MagicMock, patch

from agent_bitcoin.agents.payment_decision import PaymentDecision, PaymentDecisionAgent
from agent_bitcoin.constants import DEFAULT_MAX_PAYMENT_SATS, DEFAULT_MIN_PAYMENT_SATS


def _agent(**kwargs) -> PaymentDecisionAgent:
    with patch("agent_bitcoin.agents.payment_decision.ChatXAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        defaults = dict(
            api_key="test",
            min_sats=DEFAULT_MIN_PAYMENT_SATS,
            max_sats=DEFAULT_MAX_PAYMENT_SATS,
            confirm_above_sats=500_000,
        )
        defaults.update(kwargs)
        return PaymentDecisionAgent(**defaults)


def test_abt001_agent_allows_normal_amount_to_reach_llm():
    agent = _agent()
    agent.llm.invoke.return_value = MagicMock(content="Final decision: PAY")
    result = agent.decide_payment({"amount_sats": 50_000, "memo": "nominal"})
    agent.llm.invoke.assert_called_once()
    assert result["blocked_by_policy"] is False
    assert result["decision"] == PaymentDecision.PAY.value


def test_abt002_agent_below_minimum():
    agent = _agent()
    result = agent.decide_payment({"amount_sats": DEFAULT_MIN_PAYMENT_SATS - 1})
    assert result["decision"] == PaymentDecision.REJECT.value
    assert result["policy_code"] == "BELOW_MINIMUM"
    agent.llm.invoke.assert_not_called()


def test_abt003_agent_above_maximum():
    agent = _agent()
    result = agent.decide_payment({"amount_sats": DEFAULT_MAX_PAYMENT_SATS + 1})
    assert result["decision"] == PaymentDecision.REJECT.value
    assert result["policy_code"] == "ABOVE_MAXIMUM"
    agent.llm.invoke.assert_not_called()


def test_confirm_required_band():
    agent = _agent()
    result = agent.decide_payment({"amount_sats": 750_000, "memo": "needs human"})
    assert result["decision"] == PaymentDecision.CONFIRM_REQUIRED.value
    assert result["policy_code"] == "CONFIRM_REQUIRED"
    agent.llm.invoke.assert_not_called()


def test_invalid_amount():
    agent = _agent()
    result = agent.decide_payment({"memo": "no amount"})
    assert result["decision"] == PaymentDecision.REJECT.value
    assert result["policy_code"] == "INVALID_AMOUNT"
    agent.llm.invoke.assert_not_called()


def test_llm_prompt_truncates_payment_request():
    agent = _agent()
    agent.llm.invoke.return_value = MagicMock(content="We should REJECT this invoice.")
    result = agent.decide_payment(
        {
            "amount_sats": 5000,
            "memo": "ok",
            "payment_request": "lnbcrt" + "x" * 200,
        }
    )
    agent.llm.invoke.assert_called_once()
    assert result["decision"] == PaymentDecision.REJECT.value
    human = agent.llm.invoke.call_args[0][0][1].content
    assert "x" * 200 not in human


def test_default_agent_max_matches_shared_constant(clear_payment_env):
    with patch("agent_bitcoin.agents.payment_decision.ChatXAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        agent = PaymentDecisionAgent(api_key="test")
        assert agent.max_sats == DEFAULT_MAX_PAYMENT_SATS
        assert agent.min_sats == DEFAULT_MIN_PAYMENT_SATS
