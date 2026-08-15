"""
Shared payment policy defaults for SDK, backend API, and agents.

Env vars may still override at runtime; these are the single source of truth
for default numeric limits so invoice and agent ceilings cannot drift.

Mainnet pilot defaults (docs/mainnet-pilot.md Phase 0):
  single pay 50_000, daily 100_000, autopay off, fee sends off.
"""

from __future__ import annotations

import os

# --- Canonical defaults (sats) ---
DEFAULT_MIN_PAYMENT_SATS = 1_000
DEFAULT_MAX_PAYMENT_SATS = 1_000_000
# When LND_NETWORK=mainnet and MAX_PAYMENT_SATS unset (pilot ceiling)
DEFAULT_MAINNET_MAX_PAYMENT_SATS = 50_000
DEFAULT_MAX_DAILY_PAYMENT_SATS = 100_000
DEFAULT_MAX_FEE_SEND_SATS = 100_000
# Aperture L402 price per paid request (matches MIN_PAYMENT_SATS)
DEFAULT_L402_PRICE_SATS = 1_000


def env_int(name: str, default: int) -> int:
    """Read a positive-capable int from the environment, or return default."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


def current_network() -> str:
    return os.getenv("LND_NETWORK", "regtest").strip().lower() or "regtest"


def is_mainnet() -> bool:
    return current_network() == "mainnet"


def min_payment_sats() -> int:
    return env_int("MIN_PAYMENT_SATS", DEFAULT_MIN_PAYMENT_SATS)


def max_payment_sats() -> int:
    """
    Maximum invoice / payment amount (sats).

    MAX_INVOICE_SATS and PAYMENT_DECISION_MAX_SATS both default to this value.
    On mainnet, default ceiling is pilot 50_000 unless MAX_PAYMENT_SATS is set.
    """
    if os.getenv("MAX_PAYMENT_SATS", "").strip():
        return env_int("MAX_PAYMENT_SATS", DEFAULT_MAX_PAYMENT_SATS)
    if is_mainnet():
        return DEFAULT_MAINNET_MAX_PAYMENT_SATS
    return DEFAULT_MAX_PAYMENT_SATS


def max_daily_payment_sats() -> int:
    """
    Max sum of successful Lightning pays per UTC day (sats).

    0 = disabled (no daily cap). On mainnet defaults to pilot 100_000;
    on lab nets defaults to 0 (unlimited) unless MAX_DAILY_PAYMENT_SATS is set.
    """
    if os.getenv("MAX_DAILY_PAYMENT_SATS", "").strip():
        return env_int("MAX_DAILY_PAYMENT_SATS", 0)
    if is_mainnet():
        return DEFAULT_MAX_DAILY_PAYMENT_SATS
    return 0


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


def max_fee_send_sats() -> int:
    return env_int("MAX_FEE_SEND_SATS", DEFAULT_MAX_FEE_SEND_SATS)


def autopay_allowed() -> bool:
    """
    Whether non-interactive Lightning pay is allowed.

    Mainnet: require AGENT_BITCOIN_ALLOW_AUTOPAY=1 (human pilot default off).
    Lab nets: allowed unless AGENT_BITCOIN_ALLOW_AUTOPAY=0.
    """
    flag = (os.getenv("AGENT_BITCOIN_ALLOW_AUTOPAY") or "").strip()
    if is_mainnet():
        return flag == "1"
    if flag == "0":
        return False
    return True


def fee_send_allowed() -> bool:
    """
    Generic on-chain send (`send_onchain`).

    Mainnet: disabled unless AGENT_BITCOIN_ALLOW_MAINNET_FEE=1.
    Lab nets: allowed.
    """
    if is_mainnet():
        return (os.getenv("AGENT_BITCOIN_ALLOW_MAINNET_FEE") or "").strip() == "1"
    return True
