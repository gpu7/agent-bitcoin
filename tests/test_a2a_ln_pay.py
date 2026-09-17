"""Offline A2A LN wiring. No mainnet, no Docker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))
import a2a_ln_pay as a2a  # noqa: E402


def test_offline_invoice_and_pay() -> None:
    assert a2a.cmd_invoice(argparse.Namespace(offline=True, sats=100, memo="t")) == 0
    assert a2a.cmd_pay(argparse.Namespace(offline=True, bolt11="lnbc1offline")) == 0


def test_invoice_uses_create_invoice() -> None:
    called: list = []

    class C:
        def create_invoice(self, memo, amount_sats, expiry_seconds=3600):
            called.append((memo, amount_sats, expiry_seconds))
            return SimpleNamespace(
                payment_request="lnbc1testinvoice",
                payment_hash="ab" * 32,
                r_hash="ab" * 32,
            )

    args = argparse.Namespace(offline=False, sats=100, memo="a2a")
    assert a2a.cmd_invoice(args, client=C()) == 0
    assert called == [("a2a", 100, 3600)]


def test_pay_uses_pay_invoice() -> None:
    called: list = []

    class C:
        def pay_invoice(self, payment_request, fee_limit_sats=200):
            called.append(payment_request)
            return SimpleNamespace(
                success=True,
                status="SUCCEEDED",
                amount=100,
                payment_hash="cd" * 32,
                preimage="ee" * 32,
            )

    args = argparse.Namespace(offline=False, bolt11="lnbc1abc")
    assert a2a.cmd_pay(args, client=C()) == 0
    assert called == ["lnbc1abc"]


def test_cli_offline_help() -> None:
    import subprocess
    import sys as _sys

    proc = subprocess.run(
        [_sys.executable, str(ROOT / "examples" / "a2a_ln_pay.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "invoice" in proc.stdout
    assert "pay" in proc.stdout
    assert "invoice-dm" in proc.stdout
    assert "pay-dm" in proc.stdout


def test_payload_reject_wrong_sats() -> None:
    payload = a2a.build_invoice_payload(100, "lnbc1abc", 2_000_000_000)
    try:
        a2a.check_invoice_payload(payload, 200)
        raise AssertionError("expected wrong sats")
    except ValueError as exc:
        assert "sats" in str(exc)


def test_payload_reject_expired() -> None:
    payload = a2a.build_invoice_payload(100, "lnbc1abc", 1)
    try:
        a2a.check_invoice_payload(payload, 100, now=100)
        raise AssertionError("expected expired")
    except ValueError as exc:
        assert "expired" in str(exc)


def test_nip17_invoice_roundtrip() -> None:
    import pytest

    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    payee = PrivateKey()
    payer = PrivateKey()
    payload = a2a.build_invoice_payload(100, "lnbc1secretinvoice", 2_000_000_000)
    wrap = a2a.wrap_payload(payee, payer.public_key.hex(), payload)
    assert wrap["kind"] == 1059
    got, rumor = a2a.unwrap_payload(payer, wrap)
    assert got["bolt11"] == "lnbc1secretinvoice"
    assert rumor["pubkey"] == payee.public_key.hex()
    assert a2a.check_invoice_payload(got, 100, now=1_000) == "lnbc1secretinvoice"


def test_npub_to_hex_with_bech32() -> None:
    pytest.importorskip("bech32")
    pytest.importorskip("pynostr")
    from pynostr.key import PrivateKey

    sk = PrivateKey()
    npub = sk.public_key.bech32()
    assert a2a.npub_to_hex(npub) == sk.public_key.hex()


def test_offline_invoice_dm_no_relay() -> None:
    args = argparse.Namespace(
        offline=True,
        to_npub="npub1unused",
        sats=100,
        memo="t",
        nostr_name="a2a_payee",
    )
    assert a2a.cmd_invoice_dm(args) == 0


def test_offline_pay_dm_timeout() -> None:
    args = argparse.Namespace(
        offline=True,
        from_npub="npub1unused",
        sats=100,
        wait=0,
        nostr_name="a2a_payer",
        offline_inbox=[],
        offline_sk=None,
    )
    try:
        a2a.cmd_pay_dm(args)
        raise AssertionError("expected no DM")
    except SystemExit as exc:
        assert "no DM" in str(exc)


def test_pay_dm_live_passes_from_hex(monkeypatch) -> None:
    seen: dict = {}

    def fake_hex(npub: str) -> str:
        seen["npub"] = npub
        return "ab" * 32

    def fake_poll(sk, from_hex, sats, wait, inbox=None):
        seen["from_hex"] = from_hex
        return a2a.build_invoice_payload(100, "lnbc1x", 2_000_000_000)

    monkeypatch.setattr(a2a, "npub_to_hex", fake_hex)
    monkeypatch.setattr(a2a, "_poll_dm", fake_poll)
    monkeypatch.setattr(a2a, "_require_latches", lambda **k: None)
    monkeypatch.setattr(a2a, "_load_nostr", lambda n: object())

    class C:
        lnd = SimpleNamespace(decode_pay_req=lambda b: {"num_satoshis": 100})

        def pay_invoice(self, payment_request, fee_limit_sats=200):
            return SimpleNamespace(
                success=True,
                status="SUCCEEDED",
                amount=100,
                payment_hash="h",
                preimage="p",
            )

    args = argparse.Namespace(
        offline=False,
        from_npub="npub1abc",
        sats=100,
        wait=1,
        nostr_name="a2a_payer",
    )
    assert a2a.cmd_pay_dm(args, client=C()) == 0
    assert seen["from_hex"] == "ab" * 32
    assert seen["npub"] == "npub1abc"
