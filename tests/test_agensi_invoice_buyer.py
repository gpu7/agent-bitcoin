"""Offline checks for the Agensi invoice decode buyer path."""

from __future__ import annotations

from pathlib import Path

_SKILL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "lightning-invoice-decode-preflight"
    / "SKILL.md"
)
_DEPLOY = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "deployment"
    / "agensi_invoice_buyer.py"
)


def test_bad_invoice_without_mainnet_latch(monkeypatch):
    monkeypatch.delenv("AGENT_BITCOIN_ALLOW_MAINNET", raising=False)
    from agent_bitcoin.bolt11_invoice import inspect_payment_hashes

    assert inspect_payment_hashes("lnbc1notvalid") is None
    assert inspect_payment_hashes("") is None


def test_origin_handlers_are_present():
    from l402 import ln_invoice_decode as dec
    from l402 import ln_invoice_preflight as pf

    assert callable(dec.handle_request)
    assert callable(pf.handle_request)


def test_skill_file_has_no_wallet_secrets():
    text = _SKILL.read_text(encoding="utf-8")
    lower = text.lower()
    assert "nsec" not in lower
    assert "seed" not in lower
    assert "unlock password" not in lower
    assert "inspect_payment_hashes" in text


def test_deployment_script_does_not_pay():
    text = _DEPLOY.read_text(encoding="utf-8")
    assert "pay_invoice" not in text
