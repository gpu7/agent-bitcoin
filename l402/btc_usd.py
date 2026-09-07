"""BTC/USD pass-through digest for GET /paid/finance/btc-usd (stdlib only).

Not an FX index. Parses public JSON USD per 1 BTC and derives sats_per_usd.
Separate cache from mempool-feerate.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_URL = "https://mempool.space/api/v1/prices"
DEFAULT_TTL_S = 30
MIN_TTL_S = 30
MAX_TTL_S = 60
FETCH_TIMEOUT_S = 3.0
USER_AGENT = "agent-bitcoin-btc-usd/v1"
SERVICE = "btc-usd"
VERSION = "v1"
SOURCE = "public_price_api"
SATS_PER_BTC = 100_000_000


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
    raw = os.environ.get("BTC_USD_TTL_S", "").strip()
    if not raw:
        return DEFAULT_TTL_S
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_TTL_S
    return max(MIN_TTL_S, min(MAX_TTL_S, value))


def url_from_env() -> str:
    return (os.environ.get("BTC_USD_URL") or DEFAULT_URL).strip() or DEFAULT_URL


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _usd_per_btc(value: Any) -> float:
    n = float(value)
    if n <= 0 or n != n or n == float("inf"):
        raise ValueError("USD")
    return n


def _source_as_of_from_raw(raw: dict[str, Any], fallback: str) -> str:
    """Optional unix `time` from mempool.space /api/v1/prices → ISO-Z."""
    t = raw.get("time")
    if t is None:
        return fallback
    try:
        ts = float(t)
    except (TypeError, ValueError):
        return fallback
    if ts <= 0 or ts != ts or ts == float("inf"):
        return fallback
    try:
        return _iso_z(datetime.fromtimestamp(ts, tz=timezone.utc))
    except (OSError, OverflowError, ValueError):
        return fallback


def digest_prices(
    raw: dict[str, Any],
    *,
    now: datetime | None = None,
    ttl_s: int | None = None,
    stale: bool = False,
    source_as_of: str | None = None,
) -> dict[str, Any]:
    """Map mempool.space /api/v1/prices USD field to btc_usd + sats_per_usd.

    Accepted schema (one public JSON object):
    - ``USD`` (required): positive number, int or float — USD per 1 BTC.
    - ``time`` (optional): unix seconds; used for ``source_as_of`` when present.
    Other vendor fields (EUR, …) are ignored. Raw JSON is not attached.
    """
    if "USD" not in raw:
        raise ValueError("upstream JSON missing USD")
    btc_usd = _usd_per_btc(raw["USD"])
    as_of = _iso_z(now or _now_utc())
    ttl = DEFAULT_TTL_S if ttl_s is None else int(ttl_s)
    ttl = max(MIN_TTL_S, min(MAX_TTL_S, ttl))
    return {
        "ok": True,
        "service": SERVICE,
        "version": VERSION,
        "as_of": as_of,
        "ttl_s": ttl,
        "source": SOURCE,
        "source_as_of": source_as_of or _source_as_of_from_raw(raw, as_of),
        "stale": bool(stale),
        "btc_usd": btc_usd,
        "sats_per_usd": math.floor(SATS_PER_BTC / btc_usd),
    }


def fetch_prices(url: str, timeout: float = FETCH_TIMEOUT_S) -> dict[str, Any]:
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
    do_fetch = fetch or fetch_prices
    when = now or _now_utc()

    with _lock:
        global _cache_payload, _cache_mono
        if _cache_payload is not None and (clock() - _cache_mono) < ttl:
            return dict(_cache_payload)
        try:
            raw = do_fetch(target)
            payload = digest_prices(raw, now=when, ttl_s=ttl, stale=False)
            _cache_payload = payload
            _cache_mono = clock()
            return dict(payload)
        except (
            OSError,
            URLError,
            TimeoutError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            if _cache_payload is not None:
                stale = dict(_cache_payload)
                stale["stale"] = True
                return stale
            raise UpstreamUnavailable(str(exc) or "upstream_unavailable") from exc
