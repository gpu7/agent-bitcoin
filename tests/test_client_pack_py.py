"""Offline client_pack.py: argparse, hello schema, open refused on zero balance."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "examples" / "client-pack"
CLI = PACK / "client_pack.py"
SCHEMA = json.loads((PACK / "hello.schema.json").read_text(encoding="utf-8"))

sys.path.insert(0, str(PACK))
import client_pack as cp  # noqa: E402


def test_cli_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for name in (
        "doctor",
        "up",
        "wallet",
        "hello",
        "status",
        "address",
        "open",
        "smoke",
        "all",
    ):
        assert name in proc.stdout


@pytest.mark.parametrize(
    "sub",
    ["doctor", "up", "wallet", "hello", "status", "address", "open", "smoke", "all"],
)
def test_subcommand_help(sub: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(CLI), sub, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_write_hello_schema(tmp_path: Path) -> None:
    path = tmp_path / "client-hello.json"
    pub = "02" + ("ab" * 32)
    doc = cp.write_hello("203.0.113.10", pub, path)
    for key in SCHEMA["required"]:
        assert key in doc
    assert "seed" not in doc
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["egress_ip"] == "203.0.113.10"
    assert len(raw["identity_pubkey"]) == 66


def test_open_refused_on_zero_balance() -> None:
    args = argparse.Namespace(sats=50000)
    opened: list[tuple] = []

    def balance() -> dict:
        return {"confirmed_balance": "0"}

    def open_fn(*a: str) -> str:
        opened.append(a)
        return ""

    code = cp.cmd_open(args, balance_fn=balance, open_fn=open_fn)
    assert code == 4
    assert opened == []


def test_open_refused_below_sats() -> None:
    args = argparse.Namespace(sats=50000)
    opened: list = []
    code = cp.cmd_open(
        args,
        balance_fn=lambda: {"confirmed_balance": "1000"},
        open_fn=lambda *a: opened.append(a) or "",
    )
    assert code == 4
    assert opened == []


def test_channel_spendable_and_aws_peer() -> None:
    aws = cp.AWS_PUB
    other = "03" + ("cd" * 32)
    rows = cp.channel_status_rows(
        [
            {
                "remote_pubkey": other,
                "active": True,
                "private": False,
                "local_balance": "999",
                "remote_balance": "1",
                "local_chan_reserve_sat": "1",
                "total_satoshis_sent": "0",
            },
            {
                "remote_pubkey": aws,
                "active": True,
                "private": True,
                "local_balance": "500",
                "remote_balance": "200",
                "local_chan_reserve_sat": "100",
                "total_satoshis_sent": "42",
            },
        ]
    )
    assert len(rows) == 1
    assert rows[0]["remote_pubkey"] == aws
    assert rows[0]["approx_spendable"] == 400
    assert rows[0]["private"] is True
    assert rows[0]["total_satoshis_sent"] == 42
    tight = cp.channel_status_rows(
        [
            {
                "remote_pubkey": other,
                "local_balance": "50",
                "local_chan_reserve_sat": "80",
                "remote_balance": "0",
                "total_satoshis_sent": "0",
            }
        ]
    )
    assert tight[0]["approx_spendable"] == 0
