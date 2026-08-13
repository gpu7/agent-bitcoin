"""NWC method allowlist and amount budgets for agent-bitcoin."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from agent_bitcoin.constants import (
    is_mainnet,
    max_payment_sats,
    min_payment_sats,
)
from agent_bitcoin.nwc.errors import NWCPolicyError

# NIP-47 event kinds (for clients/services)
KIND_INFO: Final[int] = 13194
KIND_REQUEST: Final[int] = 23194
KIND_RESPONSE: Final[int] = 23195

# N6 mainnet pilot: single-pay ceiling unless NWC_MAX_PAYMENT_SATS is set lower/higher
DEFAULT_NWC_MAINNET_MAX_SATS: Final[int] = 2_000
DEFAULT_NWC_MAINNET_DAILY_SATS: Final[int] = 2_000

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


def _truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() in {"1", "true", "TRUE", "yes", "YES"}


def nwc_enabled() -> bool:
    """Master kill switch for NWC service (default off)."""
    return _truthy("AGENT_BITCOIN_NWC_ENABLE")


def nwc_mainnet_allowed() -> bool:
    """Explicit mainnet NWC go (default off; separate from LND ALLOW_MAINNET)."""
    return _truthy("AGENT_BITCOIN_NWC_ALLOW_MAINNET")


def assert_nwc_network_allowed() -> None:
    """Refuse mainnet NWC unless both enable and mainnet NWC latch are set.

    Also requires ``AGENT_BITCOIN_ALLOW_MAINNET=1`` so LNDClient can open mainnet.
    """
    if not is_mainnet():
        return
    if not nwc_enabled():
        raise NWCPolicyError(
            "NWC disabled on mainnet: set AGENT_BITCOIN_NWC_ENABLE=1",
            code="RESTRICTED",
        )
    if not nwc_mainnet_allowed():
        raise NWCPolicyError(
            "Mainnet NWC frozen: set AGENT_BITCOIN_NWC_ALLOW_MAINNET=1 only for "
            "an intentional tight-budget session (see docs/nwc-automatic-wallets.md N6)",
            code="RESTRICTED",
        )
    if os.getenv("AGENT_BITCOIN_ALLOW_MAINNET", "").strip() != "1":
        raise NWCPolicyError(
            "Mainnet NWC requires AGENT_BITCOIN_ALLOW_MAINNET=1 for LND access",
            code="RESTRICTED",
        )


@dataclass(frozen=True)
class NWCBudgetPolicy:
    """Amount policy for make_invoice / pay_invoice (sats)."""

    min_sats: int
    max_sats: int

    @classmethod
    def from_env(cls) -> NWCBudgetPolicy:
        """Build budget from env.

        Mainnet NWC defaults to a **tight** max (2_000 sats) unless
        ``NWC_MAX_PAYMENT_SATS`` is set. Lab nets use project max_payment_sats().
        """
        min_s = min_payment_sats()
        if os.getenv("NWC_MIN_PAYMENT_SATS", "").strip():
            min_s = int(os.environ["NWC_MIN_PAYMENT_SATS"])

        if os.getenv("NWC_MAX_PAYMENT_SATS", "").strip():
            max_s = int(os.environ["NWC_MAX_PAYMENT_SATS"])
        elif is_mainnet():
            max_s = DEFAULT_NWC_MAINNET_MAX_SATS
        else:
            max_s = max_payment_sats()

        if max_s < min_s:
            max_s = min_s
        return cls(min_sats=min_s, max_sats=max_s)

    @classmethod
    def mainnet_tight(cls) -> NWCBudgetPolicy:
        """N6 default: project min (1,000 sats) up to max 2k."""
        return cls(
            min_sats=min_payment_sats(),
            max_sats=DEFAULT_NWC_MAINNET_MAX_SATS,
        )


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
