"""Wait-window or named band → sat/vB from the feerate cache.

GET /paid/finance/confirm-target?minutes=30
GET /paid/finance/confirm-target?target=medium
GET /paid/finance/confirm-target?minutes=30&target=medium&vsize=250

Helix snap: 1–20 fast, 21–45 medium, 46–60 slow. minutes 1–60.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable
from urllib.parse import parse_qs

try:
    from l402 import fee_for_vsize as _ffv
    from l402 import mempool_feerate as _feerate
except ImportError:  # Docker WORKDIR /app
    import fee_for_vsize as _ffv  # type: ignore[no-redef]
    import mempool_feerate as _feerate  # type: ignore[no-redef]

SERVICE = "confirm-target"
VERSION = "v1"
TARGETS = ("fast", "medium", "slow")
_INT_RE = re.compile(r"[+-]?\d+")


class BadConfirmTarget(ValueError):
    """Missing, invalid, or conflicting minutes/target."""


def snap_minutes(minutes: int) -> str:
    if 1 <= minutes <= 20:
        return "fast"
    if 21 <= minutes <= 45:
        return "medium"
    if 46 <= minutes <= 60:
        return "slow"
    raise BadConfirmTarget("minutes")


def _one_int(qs: dict[str, list[str]], name: str) -> int | None:
    raw_list = qs.get(name)
    if not raw_list:
        return None
    if len(raw_list) != 1:
        raise BadConfirmTarget(name)
    raw = raw_list[0].strip()
    if not _INT_RE.fullmatch(raw):
        raise BadConfirmTarget(name)
    return int(raw)


def parse_request(query: str) -> tuple[str, int | None, int | None]:
    """Return (target, minutes_or_none, vsize_or_none)."""
    qs = parse_qs(query, keep_blank_values=True)
    if "weight" in qs:
        raise _ffv.BadVsize("weight")
    minutes = _one_int(qs, "minutes")
    raw_target = qs.get("target")
    target: str | None = None
    if raw_target:
        if len(raw_target) != 1:
            raise BadConfirmTarget("target")
        target = raw_target[0].strip().lower()
        if target not in TARGETS:
            raise BadConfirmTarget("target")
    if minutes is None and target is None:
        raise BadConfirmTarget("missing")
    if minutes is not None:
        snapped = snap_minutes(minutes)
        if target is not None and target != snapped:
            raise BadConfirmTarget("conflict")
        target = snapped
    vsize: int | None = None
    if "vsize" in qs:
        vsize = _ffv.parse_vsize(query)
    assert target is not None
    return target, minutes, vsize


def compute(
    target: str,
    quote: dict[str, Any],
    *,
    minutes: int | None = None,
    vsize: int | None = None,
) -> dict[str, Any]:
    sat_vb = int(quote[target])
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": quote["as_of"],
        "ttl_s": quote["ttl_s"],
        "source": quote["source"],
        "source_as_of": quote["source_as_of"],
        "stale": bool(quote.get("stale")),
        "target": target,
        "sat_vb": sat_vb,
    }
    if minutes is not None:
        out["minutes"] = minutes
    if vsize is not None:
        out["vsize"] = vsize
        out["fee_sats"] = math.ceil(vsize * sat_vb)
    return out


def quote_for_request(
    path: str,
    *,
    get_feerate: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _route, sep, query = path.partition("?")
    if not sep:
        query = ""
    target, minutes, vsize = parse_request(query)
    fetch = get_feerate or _feerate.get_quote
    rates = fetch()
    return compute(target, rates, minutes=minutes, vsize=vsize)
