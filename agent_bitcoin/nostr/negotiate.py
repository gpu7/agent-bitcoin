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


def choose_payer_n(candidates: list[tuple[str, int]]) -> tuple[str, str]:
    """Return (winner_npub, concede_reason) for two or more agents.

    Highest score pays. Tie on that score: lexicographically greater npub.
    concede_reason is ``lower_score`` or ``tie_npub``.
    """
    if len(candidates) < 2:
        raise ValueError("need at least two (npub, score) pairs")
    max_score = max(score for _npub, score in candidates)
    tied = [npub for npub, score in candidates if score == max_score]
    if len(tied) == 1:
        return tied[0], "lower_score"
    return max(tied), "tie_npub"


def choose_payer(
    alice_npub: str,
    alice_score: int,
    bob_npub: str,
    bob_score: int,
) -> tuple[str, str]:
    """Two-agent wrapper around :func:`choose_payer_n`."""
    return choose_payer_n([(alice_npub, alice_score), (bob_npub, bob_score)])


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
