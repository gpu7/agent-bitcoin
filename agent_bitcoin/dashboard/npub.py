"""Short public ids for the dashboard picture.

Reads only `.nostr-poc-mainnet/alice.pub.json`. Never opens an encrypted
nsec file, Bob's key, or the regtest and signet directories.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path

_PLACEHOLDER = "agent npub"
_NPUB = re.compile(r"^npub1([023456789acdefghjklmnpqrstuvwxyz]{8,})$")
_MAX_PUB_BYTES = 8192


def default_npub_dir() -> Path:
    """Mainnet lab pubs next to the repo. Not `.nostr-poc` or `.nostr-poc-signet`."""
    return Path(__file__).resolve().parents[2] / ".nostr-poc-mainnet"


def short_npub(value: str | None) -> str:
    """`npub1…` plus the last four bech32 characters, or the placeholder."""
    text = (value or "").strip().lower()
    if not text or "nsec" in text:
        return _PLACEHOLDER
    match = _NPUB.fullmatch(text)
    if match is None:
        return _PLACEHOLDER
    return "npub1…" + match.group(1)[-4:]


def picture_labels(
    env: Mapping[str, str] | None = None,
    npub_dir: Path | None = None,
) -> tuple[str, str]:
    """Agent 1 from the Mac payer pub, Agent 2 from `DASHBOARD_AGENT2_NPUB` only."""
    source = os.environ if env is None else env
    directory = default_npub_dir() if npub_dir is None else npub_dir
    override = (source.get("DASHBOARD_AGENT1_NPUB") or "").strip()
    raw1 = override or _read_alice_npub(directory)
    raw2 = (source.get("DASHBOARD_AGENT2_NPUB") or "").strip()
    return short_npub(raw1), short_npub(raw2)


def _read_alice_npub(directory: Path) -> str | None:
    path = directory / "alice.pub.json"
    try:
        if not path.is_file() or path.stat().st_size > _MAX_PUB_BYTES:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    npub = data.get("npub")
    if not isinstance(npub, str):
        return None
    return npub
