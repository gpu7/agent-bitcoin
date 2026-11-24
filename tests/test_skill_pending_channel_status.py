"""The pending channel skill file is present and read-only."""

from __future__ import annotations

from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "pending-channel-status"
    / "SKILL.md"
)

_FORBIDDEN = (
    "openchannel",
    "closechannel",
    "forceclose",
    "fundchannel",
    "sendpayment",
    "sendcoins",
    "pay_invoice",
)

_REQUIRED = (
    "get_info",
    "pendingchannels",
    "pending_open_channels",
    "pending_closing_channels",
    "waiting_close_channels",
    "pending_force_closing_channels",
    "capacity",
    "local_balance",
    "remote_balance",
    "initiator",
    "funding_expiry_blocks",
    "blocks_til_maturity",
    "wallet locked",
)


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    end = text.find("\n---\n", 4)
    assert end != -1
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        assert sep == ":"
        data[key.strip()] = value.strip()
    return data


def test_skill_file_has_frontmatter():
    text = _SKILL.read_text(encoding="utf-8")
    meta = _frontmatter(text)
    assert meta.get("name")
    assert meta.get("description")


def test_skill_has_no_channel_or_spend_commands():
    text = _SKILL.read_text(encoding="utf-8").lower()
    for token in _FORBIDDEN:
        assert token not in text


def test_skill_names_the_read_only_fields():
    text = _SKILL.read_text(encoding="utf-8")
    for token in _REQUIRED:
        assert token in text
