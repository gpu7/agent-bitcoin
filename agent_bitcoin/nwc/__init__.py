"""Nostr Wallet Connect (NIP-47) helpers for automatic agent wallets.

- N2: URI parse + policy allowlist (no pynostr required)
- N3: client + in-memory bus (requires optional ``.[nostr]`` / pynostr)
- N4: LND-backed service (this package)

See docs/nwc-automatic-wallets.md.
"""

from agent_bitcoin.nwc.errors import NWCError, NWCPolicyError, NWCURIError
from agent_bitcoin.nwc.flow import (
    decision_is_pay,
    nwc_pay_if_approved,
    rule_based_decision,
)
from agent_bitcoin.nwc.policy import (
    DEFAULT_NWC_MAINNET_MAX_SATS,
    KIND_INFO,
    KIND_REQUEST,
    KIND_RESPONSE,
    V1_ALLOWED_METHODS,
    NWCBudgetPolicy,
    assert_amount_sats_allowed,
    assert_method_allowed,
    assert_nwc_network_allowed,
    nwc_enabled,
    nwc_mainnet_allowed,
)
from agent_bitcoin.nwc.uri import NWCConnectionURI, build_nwc_uri, parse_nwc_uri

__all__ = [
    "DEFAULT_NWC_MAINNET_MAX_SATS",
    "KIND_INFO",
    "KIND_REQUEST",
    "KIND_RESPONSE",
    "NWCBudgetPolicy",
    "NWCConnectionURI",
    "NWCError",
    "NWCPolicyError",
    "NWCURIError",
    "V1_ALLOWED_METHODS",
    "assert_amount_sats_allowed",
    "assert_method_allowed",
    "assert_nwc_network_allowed",
    "build_nwc_uri",
    "decision_is_pay",
    "nwc_enabled",
    "nwc_mainnet_allowed",
    "nwc_pay_if_approved",
    "parse_nwc_uri",
    "rule_based_decision",
]

# Client/service stack needs pynostr (optional extra)
try:
    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import (
        NWCClient,
        attach_mock_wallet,
        sign_response_event,
    )
    from agent_bitcoin.nwc.service import NWCService, create_nwc_service

    __all__ += [
        "InMemoryNWCBus",
        "NWCClient",
        "NWCService",
        "attach_mock_wallet",
        "create_nwc_service",
        "sign_response_event",
    ]
except ImportError:  # pragma: no cover - environment without pynostr
    pass
