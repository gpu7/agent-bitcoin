"""The Nostr identity skill file is present and public-only."""

from __future__ import annotations

from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "nostr-identity-status"
    / "SKILL.md"
)

_FORBIDDEN = (
    "nsec",
    "private key",
    "sign_event",
    "privatekey",
)

_REQUIRED = (
    ".nostr-poc",
    ".nostr-poc-mainnet",
    "NOSTR_POC_DIR",
    ".pub.json",
    ".enc.json",
    "short_npub",
    "npub1",
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


def test_skill_has_no_secret_or_signing_commands():
    text = _SKILL.read_text(encoding="utf-8").lower()
    for token in _FORBIDDEN:
        assert token not in text


def test_skill_names_the_public_files():
    text = _SKILL.read_text(encoding="utf-8")
    for token in _REQUIRED:
        assert token in text
