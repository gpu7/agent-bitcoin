"""
Shared payment policy defaults for SDK, backend API, and agents.

Env vars may still override at runtime; these are the single source of truth
for default numeric limits so invoice and agent ceilings cannot drift.
"""

from __future__ import annotations

import os

# --- Canonical defaults (sats) ---
DEFAULT_MIN_PAYMENT_SATS = 2_000
DEFAULT_MAX_PAYMENT_SATS = 1_000_000
DEFAULT_FEE_AMOUNT_SATS = 1_000
DEFAULT_MAX_FEE_SEND_SATS = 100_000


def env_int(name: str, default: int) -> int:
    """Read a positive-capable int from the environment, or return default."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def min_payment_sats() -> int:
    return env_int("MIN_PAYMENT_SATS", DEFAULT_MIN_PAYMENT_SATS)


def max_payment_sats() -> int:
    """
    Maximum invoice / payment amount (sats).

    MAX_INVOICE_SATS and PAYMENT_DECISION_MAX_SATS both default to this value.
    If either env is set, that name wins for its consumer; prefer setting
    MAX_PAYMENT_SATS (or both legacy names to the same value).
    """
    if os.getenv("MAX_PAYMENT_SATS", "").strip():
        return env_int("MAX_PAYMENT_SATS", DEFAULT_MAX_PAYMENT_SATS)
    return DEFAULT_MAX_PAYMENT_SATS


def max_invoice_sats() -> int:
    """Backend invoice ceiling; defaults to shared max payment."""
    if os.getenv("MAX_INVOICE_SATS", "").strip():
        return env_int("MAX_INVOICE_SATS", DEFAULT_MAX_PAYMENT_SATS)
    return max_payment_sats()


def payment_decision_max_sats() -> int:
    """Agent hard max; defaults to shared max payment."""
    if os.getenv("PAYMENT_DECISION_MAX_SATS", "").strip():
        return env_int("PAYMENT_DECISION_MAX_SATS", DEFAULT_MAX_PAYMENT_SATS)
    return max_payment_sats()


def fee_amount_sats() -> int:
    return env_int("FEE_AMOUNT_SATS", DEFAULT_FEE_AMOUNT_SATS)


def max_fee_send_sats() -> int:
    return env_int("MAX_FEE_SEND_SATS", DEFAULT_MAX_FEE_SEND_SATS)
