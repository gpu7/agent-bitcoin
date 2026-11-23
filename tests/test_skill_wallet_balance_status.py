"""The wallet balance skill file is present and read-only."""

from __future__ import annotations

from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "wallet-balance-status"
    / "SKILL.md"
)

_FORBIDDEN = (
    "sendpayment",
    "sendcoins",
    "send_coins",
    "pay_invoice",
    "fundchannel",
    "openchannel",
    "closechannel",
    "open_channel",
    "close_channel",
)

_REQUIRED = (
    "get_balance",
    "get_channel_balance",
    "get_info",
    "confirmed_balance",
    "unconfirmed_balance",
    "local_balance",
    "remote_balance",
    "pending_open_local_balance",
    "alias",
    "identity_pubkey",
    "block_height",
    "synced_to_chain",
    "synced_to_graph",
    "num_peers",
    "num_active_channels",
    "walletbalance",
    "channelbalance",
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


def test_skill_has_no_spend_or_channel_commands():
    text = _SKILL.read_text(encoding="utf-8").lower()
    for token in _FORBIDDEN:
        assert token not in text


def test_skill_names_the_read_only_fields():
    text = _SKILL.read_text(encoding="utf-8")
    for token in _REQUIRED:
        assert token in text
