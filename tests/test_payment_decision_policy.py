"""Coded policy limits for PaymentDecisionAgent (no live LLM calls)."""

from unittest.mock import MagicMock, patch

from agent_bitcoin.agents.payment_decision import PaymentDecision, PaymentDecisionAgent


def _agent(**kwargs) -> PaymentDecisionAgent:
    with patch("agent_bitcoin.agents.payment_decision.ChatXAI") as mock_cls:
        mock_cls.return_value = MagicMock()
        return PaymentDecisionAgent(
            api_key="test",
            min_sats=2000,
            max_sats=100_000,
            confirm_above_sats=50_000,
            **kwargs,
        )


def test_reject_below_minimum():
    agent = _agent()
    result = agent.decide_payment({"amount_sats": 500, "memo": "tiny"})
    assert result["decision"] == PaymentDecision.REJECT.value
    assert result["blocked_by_policy"] is True
    assert result["policy_code"] == "BELOW_MINIMUM"
    agent.llm.invoke.assert_not_called()


def test_reject_above_maximum():
    agent = _agent()
    result = agent.decide_payment({"amount_sats": 250_000, "memo": "huge"})
    assert result["decision"] == PaymentDecision.REJECT.value
    assert result["policy_code"] == "ABOVE_MAXIMUM"
    agent.llm.invoke.assert_not_called()


def test_confirm_required_band():
    agent = _agent()
    result = agent.decide_payment({"amount_sats": 75_000, "memo": "mid-large"})
    assert result["decision"] == PaymentDecision.CONFIRM_REQUIRED.value
    assert result["policy_code"] == "CONFIRM_REQUIRED"
    agent.llm.invoke.assert_not_called()


def test_invalid_amount():
    agent = _agent()
    result = agent.decide_payment({"memo": "no amount"})
    assert result["decision"] == PaymentDecision.REJECT.value
    assert result["policy_code"] == "INVALID_AMOUNT"
    agent.llm.invoke.assert_not_called()


def test_llm_only_when_within_policy():
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
    assert result["blocked_by_policy"] is False
    assert result["decision"] == PaymentDecision.REJECT.value
    # Prompt must not contain full payment request
    call_messages = agent.llm.invoke.call_args[0][0]
    human = call_messages[1].content
    assert "x" * 200 not in human
