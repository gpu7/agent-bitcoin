"""The invoice list skill file is present and read-only."""

from __future__ import annotations

from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[1] / "skills" / "invoice-list-status" / "SKILL.md"
)

_FORBIDDEN = (
    "addinvoice",
    "create_invoice",
    "cancelinvoice",
    "settleinvoice",
    "pay_invoice",
    "sendpayment",
)

_REQUIRED = (
    "get_info",
    "listinvoices",
    "max_invoices",
    "pending_only",
    "r_hash",
    "value",
    "memo",
    "settled",
    "creation_date",
    "expiry",
    "amt_paid_sat",
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


def test_skill_has_no_invoice_mutation_commands():
    text = _SKILL.read_text(encoding="utf-8").lower()
    for token in _FORBIDDEN:
        assert token not in text


def test_skill_names_the_read_only_fields():
    text = _SKILL.read_text(encoding="utf-8")
    for token in _REQUIRED:
        assert token in text
