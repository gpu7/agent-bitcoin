"""Durable daily spend ledger for payment kill-switch (Phase 2)."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def default_ledger_path() -> Path:
    override = (os.getenv("AGENT_BITCOIN_SPEND_LEDGER") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "agent-bitcoin" / "spend-ledger.json"


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _empty_day(day: str) -> dict[str, Any]:
    return {"date": day, "spent_sats": 0, "payments": []}


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_day(_utc_today())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_day(_utc_today())
    if not isinstance(data, dict):
        return _empty_day(_utc_today())
    day = _utc_today()
    if data.get("date") != day:
        return _empty_day(day)
    data.setdefault("spent_sats", 0)
    data.setdefault("payments", [])
    return data


def _save(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def spent_today_sats(path: Path | None = None) -> int:
    p = path or default_ledger_path()
    with _lock:
        data = _load(p)
        try:
            return int(data.get("spent_sats", 0))
        except (TypeError, ValueError):
            return 0


def assert_can_spend(
    amount_sats: int, max_daily_sats: int, path: Path | None = None
) -> None:
    """Raise ValueError if amount would exceed daily cap (max_daily_sats<=0 disables)."""
    if max_daily_sats <= 0:
        return
    if amount_sats <= 0:
        return
    spent = spent_today_sats(path)
    if spent + amount_sats > max_daily_sats:
        raise ValueError(
            f"Daily payment limit exceeded: spent={spent} + amount={amount_sats} "
            f"> MAX_DAILY_PAYMENT_SATS={max_daily_sats}"
        )


def record_spend(
    amount_sats: int,
    *,
    payment_hash: str | None = None,
    path: Path | None = None,
) -> int:
    """Record a successful payment; return new spent_today total."""
    if amount_sats <= 0:
        return spent_today_sats(path)
    p = path or default_ledger_path()
    with _lock:
        data = _load(p)
        try:
            spent = int(data.get("spent_sats", 0))
        except (TypeError, ValueError):
            spent = 0
        spent += int(amount_sats)
        data["spent_sats"] = spent
        payments = data.setdefault("payments", [])
        if isinstance(payments, list):
            payments.append(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "amount_sats": int(amount_sats),
                    "payment_hash": payment_hash or "",
                }
            )
        _save(p, data)
        return spent
