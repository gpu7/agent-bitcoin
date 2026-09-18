"""Offline agent-to-agent-pay wrapper. No LND, relays, xAI, or Ollama daemon."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "examples" / "agent-to-agent-pay.py"
sys.path.insert(0, str(ROOT / "examples"))


def _load():
    spec = importlib.util.spec_from_file_location("a2a_wrap", CLI)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_help() -> None:
    pytest.importorskip("pynostr")
    proc = subprocess.run(
        [sys.executable, str(CLI), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--role" in proc.stdout
    assert "--model" in proc.stdout


def test_no_llm_plus_model_errors() -> None:
    pytest.importorskip("pynostr")
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--role",
            "payer",
            "--no-llm",
            "--model",
            "grok",
            "--from-npub",
            "npub1abc",
            "--offline",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "--no-llm" in out and "--model" in out


def test_offline_payee_sent() -> None:
    pytest.importorskip("pynostr")
    proc = subprocess.run(
        [sys.executable, str(CLI), "--role", "payee", "--offline", "--sats", "100"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "sent" in proc.stdout.lower()


def test_offline_payer_no_dm() -> None:
    pytest.importorskip("pynostr")
    proc = subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--role",
            "payer",
            "--offline",
            "--from-npub",
            "npub1abc",
            "--no-llm",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "no DM" in (proc.stdout + proc.stderr)


def test_force_vote_no_skips_pay(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    pytest.importorskip("pynostr")
    pytest.importorskip("bech32")
    import a2a_ln_pay as low
    from pynostr.key import PrivateKey

    mod = _load()
    payee = PrivateKey()
    payer = PrivateKey()
    payload = low.build_invoice_payload(100, "lnbc1test", 2_000_000_000)
    wrap = low.wrap_payload(payee, payer.public_key.hex(), payload)
    monkeypatch.setenv("A2A_LLM_FORCE_VOTE", "NO")
    args = mod._parse(
        [
            "--role",
            "payer",
            "--offline",
            "--from-npub",
            payee.public_key.bech32(),
            "--model",
            "grok",
            "--sats",
            "100",
        ]
    )
    args.offline_inbox = [wrap]
    args.offline_sk = payer
    assert mod.run_payer(args) == 0
    out = capsys.readouterr().out
    assert "skip pay" in out
    assert "would pay" not in out
