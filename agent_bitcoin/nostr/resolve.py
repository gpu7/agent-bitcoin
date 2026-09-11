"""Pluggable swarm resolvers: hash stays in negotiate.py; puzzles live here.

No I/O, no pynostr, no LND. Win checks are coded — never trust an LLM answer.
"""

from __future__ import annotations

import math
from typing import Any

PUZZLE_FEE_SATS = "fee-sats"
DEFAULT_VSIZE = 141
DEFAULT_SAT_VB = 4
DEFAULT_FEE_SATS_ANSWER = 564  # ceil(141 * 4)


def fee_sats_expected(vsize: int, sat_vb: int) -> int:
    """Integer sats: ceil(vsize * sat_vb)."""
    return int(math.ceil(int(vsize) * int(sat_vb)))


def fee_sats_problem(
    vsize: int = DEFAULT_VSIZE, sat_vb: int = DEFAULT_SAT_VB
) -> dict[str, Any]:
    vs, vb = int(vsize), int(sat_vb)
    return {
        "type": "problem",
        "puzzle_type": PUZZLE_FEE_SATS,
        "vsize": vs,
        "sat_vb": vb,
        "text": (
            f"Fee in sats: ceil(vsize * sat_vb). vsize={vs} sat_vb={vb}. Integer sats."
        ),
    }


def check_solved(payload: dict[str, Any], problem: dict[str, Any]) -> bool:
    """True iff payload is a correct fee-sats solve for this problem."""
    if not isinstance(payload, dict) or not isinstance(problem, dict):
        return False
    if payload.get("type") != "solved":
        return False
    if problem.get("puzzle_type") != PUZZLE_FEE_SATS:
        return False
    if payload.get("puzzle_type") != PUZZLE_FEE_SATS:
        return False
    try:
        vsize = int(payload["vsize"])
        sat_vb = int(payload["sat_vb"])
        answer = int(payload["answer"])
        p_vs = int(problem["vsize"])
        p_vb = int(problem["sat_vb"])
    except (KeyError, TypeError, ValueError):
        return False
    if vsize != p_vs or sat_vb != p_vb:
        return False
    return answer == fee_sats_expected(p_vs, p_vb)


def pick_first_correct(
    solved: list[tuple[float, str, dict[str, Any]]],
    problem: dict[str, Any],
) -> str | None:
    """Winner npub: valid solves only, earliest mtime then larger-lex npub last.

    Sort key is (mtime, npub) so the first correct file on a file bus wins.
    """
    ok = [
        (mtime, npub, payload)
        for mtime, npub, payload in solved
        if check_solved(payload, problem)
    ]
    if not ok:
        return None
    ok.sort(key=lambda row: (row[0], row[1]))
    return ok[0][1]
