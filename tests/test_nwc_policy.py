"""Unit tests for NWC method allowlist and amount budgets."""

from __future__ import annotations

import pytest

from agent_bitcoin.nwc import (
    V1_ALLOWED_METHODS,
    NWCBudgetPolicy,
    NWCPolicyError,
    assert_amount_sats_allowed,
    assert_method_allowed,
    nwc_enabled,
)
from agent_bitcoin.nwc.policy import msats_to_sats, sats_to_msats


def test_v1_allowlist_contains_core_methods() -> None:
    assert "pay_invoice" in V1_ALLOWED_METHODS
    assert "make_invoice" in V1_ALLOWED_METHODS
    assert "get_balance" in V1_ALLOWED_METHODS
    assert "get_info" in V1_ALLOWED_METHODS


def test_allowed_methods_ok() -> None:
    for m in V1_ALLOWED_METHODS:
        assert_method_allowed(m)


def test_denied_and_unknown_methods() -> None:
    with pytest.raises(NWCPolicyError) as ei:
        assert_method_allowed("multi_pay_invoice")
    assert ei.value.code == "RESTRICTED"

    with pytest.raises(NWCPolicyError) as ei2:
        assert_method_allowed("open_channel")
    assert ei2.value.code == "NOT_IMPLEMENTED"


def test_amount_bounds() -> None:
    pol = NWCBudgetPolicy(min_sats=2000, max_sats=50_000)
    assert_amount_sats_allowed(2000, policy=pol)
    assert_amount_sats_allowed(50_000, policy=pol)
    with pytest.raises(NWCPolicyError, match="below minimum"):
        assert_amount_sats_allowed(1999, policy=pol)
    with pytest.raises(NWCPolicyError, match="exceeds maximum") as ei:
        assert_amount_sats_allowed(50_001, policy=pol)
    assert ei.value.code == "QUOTA_EXCEEDED"


def test_nwc_enable_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENT_BITCOIN_NWC_ENABLE", raising=False)
    assert nwc_enabled() is False
    with pytest.raises(NWCPolicyError, match="NWC disabled"):
        assert_amount_sats_allowed(
            2000,
            policy=NWCBudgetPolicy(2000, 50_000),
            require_enable=True,
        )
    monkeypatch.setenv("AGENT_BITCOIN_NWC_ENABLE", "1")
    assert nwc_enabled() is True
    assert_amount_sats_allowed(
        2000,
        policy=NWCBudgetPolicy(2000, 50_000),
        require_enable=True,
    )


def test_msat_helpers() -> None:
    assert sats_to_msats(2000) == 2_000_000
    assert msats_to_sats(2_000_000) == 2000
    assert msats_to_sats(2_000_999) == 2000
