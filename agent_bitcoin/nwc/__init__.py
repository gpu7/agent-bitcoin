"""Nostr Wallet Connect (NIP-47) helpers for automatic agent wallets.

Phase N2: URI parse + policy allowlist (offline).
Client/service (N3–N4) land in follow-up PRs — see docs/nwc-automatic-wallets.md.
"""

from agent_bitcoin.nwc.errors import NWCError, NWCPolicyError, NWCURIError
from agent_bitcoin.nwc.policy import (
    KIND_INFO,
    KIND_REQUEST,
    KIND_RESPONSE,
    V1_ALLOWED_METHODS,
    NWCBudgetPolicy,
    assert_amount_sats_allowed,
    assert_method_allowed,
    nwc_enabled,
)
from agent_bitcoin.nwc.uri import NWCConnectionURI, build_nwc_uri, parse_nwc_uri

__all__ = [
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
    "build_nwc_uri",
    "nwc_enabled",
    "parse_nwc_uri",
]
