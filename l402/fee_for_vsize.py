"""Total on-chain fee sats for a vsize, using mempool-feerate bands.

GET /paid/finance/fee-for-vsize?vsize=<int>
fee_sats_* = ceil(vsize * sat_vb_*). vsize is virtual bytes, not weight.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable
from urllib.parse import parse_qs

try:
    from l402 import mempool_feerate as _feerate
except ImportError:  # Docker WORKDIR /app
    import mempool_feerate as _feerate  # type: ignore[no-redef]

VSIZE_MIN = 110
VSIZE_MAX = 100_000
SERVICE = "fee-for-vsize"
VERSION = "v1"
_INT_RE = re.compile(r"[+-]?\d+")


class BadVsize(ValueError):
    """Missing, non-integer, out of range, or weight= present."""


def parse_vsize(query: str) -> int:
    qs = parse_qs(query, keep_blank_values=True)
    if "weight" in qs:
        raise BadVsize("weight")
    raw_list = qs.get("vsize")
    if not raw_list or len(raw_list) != 1:
        raise BadVsize("vsize")
    raw = raw_list[0].strip()
    if not _INT_RE.fullmatch(raw):
        raise BadVsize("vsize")
    n = int(raw)
    if n < VSIZE_MIN or n > VSIZE_MAX:
        raise BadVsize("vsize")
    return n


def compute(vsize: int, quote: dict[str, Any]) -> dict[str, Any]:
    """Multiply vsize by feerate bands; inherit envelope from the snapshot."""
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": quote["as_of"],
        "ttl_s": quote["ttl_s"],
        "source": quote["source"],
        "source_as_of": quote["source_as_of"],
        "stale": bool(quote.get("stale")),
        "vsize": int(vsize),
        "fee_sats_fast": math.ceil(vsize * quote["fast"]),
        "fee_sats_medium": math.ceil(vsize * quote["medium"]),
        "fee_sats_slow": math.ceil(vsize * quote["slow"]),
    }
    return out


def quote_for_request(
    path: str,
    *,
    get_feerate: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    _route, sep, query = path.partition("?")
    if not sep:
        query = ""
    vsize = parse_vsize(query)
    fetch = get_feerate or _feerate.get_quote
    rates = fetch()
    return compute(vsize, rates)
