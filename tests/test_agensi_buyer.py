"""Offline checks for the public Agensi buyer path.

The live LND probe and the settlement phase stay in
``tests/deployment/agensi_public_buyer.py``. They are not collected here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from agent_bitcoin.exceptions import ConfigurationError

_PROBE_PATH = Path(__file__).resolve().parent / "deployment" / "agensi_public_buyer.py"
_SPEC = importlib.util.spec_from_file_location("agensi_public_buyer", _PROBE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_PROBE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_PROBE)


def test_pay_invoice_is_exported():
    import agent_bitcoin

    assert callable(agent_bitcoin.pay_invoice)
    assert "pay_invoice" in agent_bitcoin.__all__


def test_empty_invoice_does_not_call_lncli(clear_payment_env, monkeypatch):
    calls: list[object] = []

    class FakeLND:
        def __init__(self) -> None:
            calls.append("init")

        def _run(self, *args: object) -> dict:
            calls.append(args)
            return {}

    monkeypatch.setattr("agent_bitcoin.client.LNDClient", FakeLND)
    from agent_bitcoin import pay_invoice

    with pytest.raises(ValueError, match="Payment request"):
        pay_invoice("")
    assert calls == ["init"]


def test_mainnet_without_latch_refuses_before_pay(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    from agent_bitcoin import pay_invoice

    with pytest.raises(ConfigurationError, match="ALLOW_MAINNET"):
        pay_invoice("lnbc1fake")


def test_mainnet_autopay_blocks_before_send(clear_payment_env, monkeypatch):
    monkeypatch.setenv("LND_NETWORK", "mainnet")
    monkeypatch.setenv("AGENT_BITCOIN_ALLOW_MAINNET", "1")
    sent: list[object] = []

    class FakeLND:
        def __init__(self) -> None:
            return None

        def pay_invoice(self, *args: object, **kwargs: object) -> object:
            sent.append(args)
            return None

        def _run(self, *args: object) -> dict:
            sent.append(args)
            return {}

    monkeypatch.setattr("agent_bitcoin.client.LNDClient", FakeLND)
    from agent_bitcoin import pay_invoice

    with pytest.raises(RuntimeError, match="ALLOW_AUTOPAY"):
        pay_invoice("lnbc1fake")
    assert sent == []


def test_probe_hides_pubkey_and_refuses_nsec():
    pubkey = "02" + ("ab" * 32)
    line = _PROBE.format_lnd_probe(
        {
            "synced_to_chain": True,
            "alias": "lab",
            "identity_pubkey": pubkey,
            "uris": [f"{pubkey}@203.0.113.5:9735"],
        }
    )
    assert line == "lnd_reachable=yes synced_to_chain=True alias=lab identity=present"
    assert pubkey not in line
    assert "9735" not in line
    with pytest.raises(ValueError, match="nsec"):
        _PROBE.format_lnd_probe({"alias": "nsec1example", "identity_pubkey": pubkey})
