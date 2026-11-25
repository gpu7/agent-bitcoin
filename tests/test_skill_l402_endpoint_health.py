"""The L402 health skill file is present and does not complete a challenge."""

from __future__ import annotations

from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[1] / "skills" / "l402-endpoint-health" / "SKILL.md"
)

_FORBIDDEN = (
    "pay_invoice",
    "sendpayment",
    "create_invoice",
    "addinvoice",
    "settleinvoice",
    ".fetch(",
)

_REQUIRED = (
    "parse_www_authenticate",
    "/health",
    "/paid/hello",
    "402",
    "WWW-Authenticate",
    "macaroon",
    "invoice",
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


def test_skill_has_no_pay_or_settle_commands():
    text = _SKILL.read_text(encoding="utf-8").lower()
    for token in _FORBIDDEN:
        assert token not in text


def test_skill_names_the_health_checks():
    text = _SKILL.read_text(encoding="utf-8")
    for token in _REQUIRED:
        assert token in text
