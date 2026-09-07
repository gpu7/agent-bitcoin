"""Mempool fullness for GET /paid/finance/mempool-backlog (stdlib only).

Not a mempool.space replacement. Digests public mempool counts into tx_count /
vsize / total_fee_sats. Separate from fee bands (mempool-feerate).
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "https://mempool.space/api/mempool"
DEFAULT_TTL_S = 30
MIN_TTL_S = 15
MAX_TTL_S = 60
FETCH_TIMEOUT_S = 3.0
USER_AGENT = "agent-bitcoin-mempool-backlog/v1"
SERVICE = "mempool-backlog"
VERSION = "v1"
SOURCE = "public_mempool_api"
VBYTES_PER_BLOCK = 1_000_000


class UpstreamUnavailable(Exception):
    """No usable quote: fetch failed and there is no cache."""


_lock = threading.Lock()
_cache_payload: dict[str, Any] | None = None
_cache_mono: float = 0.0


def reset_cache() -> None:
    global _cache_payload, _cache_mono
    with _lock:
        _cache_payload = None
        _cache_mono = 0.0


def ttl_s_from_env() -> int:
    raw = os.environ.get("MEMPOOL_BACKLOG_TTL_S", "").strip()
    if not raw:
        return DEFAULT_TTL_S
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_S
    return max(MIN_TTL_S, min(MAX_TTL_S, value))


def url_from_env() -> str:
    return (os.environ.get("MEMPOOL_BACKLOG_URL") or DEFAULT_URL).strip() or DEFAULT_URL


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _nonneg_int(value: Any) -> int:
    n = int(round(float(value)))
    return n if n >= 0 else 0


def digest_mempool(
    raw: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_s: int | None = None,
    stale: bool = False,
    source_as_of: str | None = None,
) -> dict[str, Any]:
    """Map mempool.space /api/mempool to fullness fields."""
    for key in ("count", "vsize"):
        if key not in raw:
            raise ValueError(f"upstream JSON missing {key!r}")
    as_of = _iso_z(now or _now_utc())
    ttl = DEFAULT_TTL_S if ttl_s is None else int(ttl_s)
    ttl = max(MIN_TTL_S, min(MAX_TTL_S, ttl))
    vsize = _nonneg_int(raw["vsize"])
    out: dict[str, Any] = {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": as_of,
        "ttl_s": ttl,
        "tx_count": _nonneg_int(raw["count"]),
        "vsize": vsize,
        "vsize_per_block_equiv": vsize / VBYTES_PER_BLOCK,
        "source": SOURCE,
        "source_as_of": source_as_of or as_of,
        "stale": bool(stale),
    }
    if "total_fee" in raw:
        out["total_fee_sats"] = _nonneg_int(raw["total_fee"])
    return out


def fetch_mempool(url: str, timeout: float = FETCH_TIMEOUT_S) -> dict[str, Any]:
    req = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read()
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("upstream JSON is not an object")
    return data


def get_quote(
    *,
    fetch: Callable[[str], dict[str, Any]] | None = None,
    url: str | None = None,
    ttl_s: int | None = None,
    now: datetime | None = None,
    monotonic: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Return a cached or freshly fetched digest. Thread-safe; one fetch at a time."""
    clock = monotonic or time.monotonic
    ttl = (
        ttl_s_from_env()
        if ttl_s is None
        else max(MIN_TTL_S, min(MAX_TTL_S, int(ttl_s)))
    )
    target = url if url is not None else url_from_env()
    do_fetch = fetch or fetch_mempool
    when = now or _now_utc()

    with _lock:
        global _cache_payload, _cache_mono
        if _cache_payload is not None and (clock() - _cache_mono) < ttl:
            return dict(_cache_payload)
        try:
            raw = do_fetch(target)
            payload = digest_mempool(raw, now=when, ttl_s=ttl, stale=False)
            _cache_payload = payload
            _cache_mono = clock()
            return dict(payload)
        except (
            OSError,
            URLError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            if _cache_payload is not None:
                stale = dict(_cache_payload)
                stale["stale"] = True
                return stale
            raise UpstreamUnavailable(str(exc) or "upstream_unavailable") from exc
