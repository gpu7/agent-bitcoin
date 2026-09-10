"""Deterministic L402 payer selection for the two-agent swarm demo.

No I/O, no pynostr, no LND. Callers sign and transport events themselves.
"""

from __future__ import annotations

import hashlib
from typing import Any

COORD_TAG = "agent-bitcoin-swarm-l402-v1"
DEFAULT_L402_URL = "http://127.0.0.1:8081/paid/finance/mempool-feerate"
DEFAULT_PRICE_SATS = 100


def invoice_id_for_url(url: str) -> str:
    """Stable 16-hex id so two terminals agree without a session file."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def negotiate_score_hex(
    pubkey_hex: str, invoice_id: str, round_n: int
) -> tuple[int, str]:
    """score, score_hex from sha256(pubkey || invoice_id || round)[:8]."""
    pk = str(pubkey_hex).strip().lower()
    msg = f"{pk}{invoice_id}{int(round_n)}".encode("utf-8")
    digest = hashlib.sha256(msg).hexdigest()
    hx = digest[:8]
    return int(hx, 16), hx


def negotiate_score(pubkey_hex: str, invoice_id: str, round_n: int) -> int:
    return negotiate_score_hex(pubkey_hex, invoice_id, round_n)[0]


def choose_payer(
    alice_npub: str,
    alice_score: int,
    bob_npub: str,
    bob_score: int,
) -> tuple[str, str]:
    """Return (winner_npub, concede_reason).

    Higher score pays. Tie: lexicographically greater npub pays.
    concede_reason is ``lower_score`` or ``tie_npub``.
    """
    if alice_score != bob_score:
        winner = alice_npub if alice_score > bob_score else bob_npub
        return winner, "lower_score"
    return max(alice_npub, bob_npub), "tie_npub"


def fee_band_summary(payload: Any) -> dict[str, int]:
    """Keep fast/medium/slow integers only. Empty dict if none."""
    if not isinstance(payload, dict):
        return {}
    out: dict[str, int] = {}
    for key in ("fast", "medium", "slow"):
        if key not in payload:
            continue
        try:
            out[key] = int(payload[key])
        except (TypeError, ValueError):
            continue
    return out
