"""Offline eight-agent swarm L402. No live LND / mainnet."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_bitcoin.nostr.negotiate import choose_payer, choose_payer_n

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "swarm_l402_negotiate.py"


def test_choose_payer_n_highest_score() -> None:
    cands = [(f"npub{i}", i) for i in range(1, 9)]
    winner, reason = choose_payer_n(cands)
    assert winner == "npub8"
    assert reason == "lower_score"


def test_choose_payer_n_tie_greater_npub() -> None:
    cands = [(f"npub{i}", 1) for i in range(1, 9)]
    winner, reason = choose_payer_n(cands)
    assert winner == "npub8"
    assert reason == "tie_npub"


def test_choose_payer_n_matches_two_agent_wrapper() -> None:
    a = choose_payer("npub1aaa", 10, "npub1zzz", 3)
    b = choose_payer_n([("npub1aaa", 10), ("npub1zzz", 3)])
    assert a == b


def _cli_env(
    monkeypatch: pytest.MonkeyPatch, extra: dict[str, str] | None = None
) -> dict[str, str]:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_BITCOIN_ALLOW_MAINNET", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    if extra:
        env.update(extra)
    return env


def test_offline_eight_cli_one_mock_pay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "all",
            "--expect-peers",
            "8",
            "--offline-bus",
            "--no-llm",
            "--force-new-keys",
            "--dir",
            str(tmp_path),
            "--timeout",
            "30",
        ],
        cwd=str(ROOT),
        env=_cli_env(monkeypatch),
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert out.count("[l402] --offline-bus mock GET") == 1
    assert "paid=True" in out
    assert "nsec1" not in out.lower()
    assert "create_client" not in out
    npubs = {
        line.split("npub=", 1)[1].split()[0]
        for line in out.splitlines()
        if "npub=npub1" in line
    }
    assert len(npubs) == 8
    bus = tmp_path / "bus"
    names = {p.name for p in bus.glob("*.json")}
    for i in range(1, 9):
        assert any(n.endswith(f"_a{i}_negotiate.json") for n in names)
    results = [p for p in bus.glob("*_result.json")]
    assert len(results) == 1
    payload = json.loads(json.loads(results[0].read_text(encoding="utf-8"))["content"])
    assert payload["type"] == "result"
    assert payload["paid"] is True
    assert "preimage" not in payload
