"""NWC method allowlist and amount budgets for agent-bitcoin."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from agent_bitcoin.constants import max_payment_sats, min_payment_sats
from agent_bitcoin.nwc.errors import NWCPolicyError

# NIP-47 event kinds (for clients/services)
KIND_INFO: Final[int] = 13194
KIND_REQUEST: Final[int] = 23194
KIND_RESPONSE: Final[int] = 23195

# v1 methods (see docs/nwc-automatic-wallets.md)
V1_ALLOWED_METHODS: Final[frozenset[str]] = frozenset(
    {
        "get_info",
        "get_balance",
        "make_invoice",
        "pay_invoice",
    }
)

V1_DENIED_METHODS: Final[frozenset[str]] = frozenset(
    {
        "multi_pay_invoice",
        "pay_keysend",
        "multi_pay_keysend",
    }
)


def nwc_enabled() -> bool:
    """Master kill switch for NWC service (default off)."""
    return os.getenv("AGENT_BITCOIN_NWC_ENABLE", "0").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }


@dataclass(frozen=True)
class NWCBudgetPolicy:
    """Amount policy for make_invoice / pay_invoice (sats)."""

    min_sats: int
    max_sats: int

    @classmethod
    def from_env(cls) -> NWCBudgetPolicy:
        return cls(min_sats=min_payment_sats(), max_sats=max_payment_sats())


def assert_method_allowed(method: str) -> None:
    """Raise if method is not in the v1 allowlist."""
    name = (method or "").strip()
    if not name:
        raise NWCPolicyError("empty method", code="NOT_IMPLEMENTED")
    if name in V1_DENIED_METHODS:
        raise NWCPolicyError(
            f"method {name!r} is denied by agent-bitcoin NWC v1 policy",
            code="RESTRICTED",
        )
    if name not in V1_ALLOWED_METHODS:
        raise NWCPolicyError(
            f"method {name!r} is not implemented in NWC v1 "
            f"(allowed: {sorted(V1_ALLOWED_METHODS)})",
            code="NOT_IMPLEMENTED",
        )


def assert_amount_sats_allowed(
    amount_sats: int,
    *,
    policy: NWCBudgetPolicy | None = None,
    require_enable: bool = False,
) -> None:
    """Enforce min/max sats for invoice/pay paths.

    Args:
        amount_sats: Amount in whole satoshis (not msats).
        policy: Budget policy; defaults to env-backed project limits.
        require_enable: If True, also require AGENT_BITCOIN_NWC_ENABLE=1.
    """
    if require_enable and not nwc_enabled():
        raise NWCPolicyError(
            "NWC disabled: set AGENT_BITCOIN_NWC_ENABLE=1 to allow wallet ops",
            code="RESTRICTED",
        )
    pol = policy or NWCBudgetPolicy.from_env()
    try:
        amt = int(amount_sats)
    except (TypeError, ValueError) as e:
        raise NWCPolicyError("amount_sats must be an integer", code="OTHER") from e
    if amt < pol.min_sats:
        raise NWCPolicyError(
            f"amount {amt} sats below minimum {pol.min_sats}",
            code="OTHER",
        )
    if amt > pol.max_sats:
        raise NWCPolicyError(
            f"amount {amt} sats exceeds maximum {pol.max_sats}",
            code="QUOTA_EXCEEDED",
        )


def msats_to_sats(msats: int) -> int:
    """Convert millisatoshis to whole sats (floor)."""
    return int(msats) // 1000


def sats_to_msats(sats: int) -> int:
    return int(sats) * 1000
