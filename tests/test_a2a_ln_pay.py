"""Offline A2A LN wiring. No mainnet, no Docker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

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
