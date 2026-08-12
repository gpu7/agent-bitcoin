"""NWC / NIP-47 related errors."""

from __future__ import annotations

from agent_bitcoin.exceptions import AgentBitcoinError


class NWCError(AgentBitcoinError):
    """Base error for Nostr Wallet Connect."""


class NWCURIError(NWCError):
    """Invalid or unsupported NWC connection URI."""


class NWCPolicyError(NWCError):
    """Method or amount rejected by local NWC policy."""

    def __init__(self, message: str, *, code: str = "RESTRICTED") -> None:
        super().__init__(message)
        self.code = code
