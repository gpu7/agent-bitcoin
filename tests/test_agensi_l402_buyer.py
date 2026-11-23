"""Offline checks for the Agensi L402 merchant buyer path."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_bitcoin.exceptions import ConfigurationError

_SKILL = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "agent-to-merchant-l402"
    / "SKILL.md"
)


def test_l402_client_fetch_is_exported():
    import agent_bitcoin

    assert callable(agent_bitcoin.L402Client.fetch)
    assert "L402Client" in agent_bitcoin.__all__


def test_mainnet_without_latch_refuses_l402_client(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("LND_TRANSPORT", "docker")
    from agent_bitcoin import L402Client, create_client

    with pytest.raises(ConfigurationError, match="ALLOW_MAINNET"):
        L402Client(create_client())


def test_mainnet_autopay_blocks_before_send(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("LND_TRANSPORT", "docker")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    sent: list[object] = []

    class FakeLND:
        def __init__(self) -> None:
            return None

        def pay_invoice(self, *args: object, **kwargs: object) -> object:
            sent.append(args)
            return None

    monkeypatch.setattr("agent_bitcoin.client.LNDClient", FakeLND)
    from agent_bitcoin import pay_invoice

    with pytest.raises(RuntimeError, match="ALLOW_AUTOPAY"):
        pay_invoice("lnbc1dryrun")
    assert sent == []


def test_skill_file_has_no_wallet_secrets():
    text = _SKILL.read_text(encoding="utf-8").lower()
    assert "nsec" not in text
    assert "seed" not in text
    assert "unlock password" not in text
    assert "L402Client" in _SKILL.read_text(encoding="utf-8")
