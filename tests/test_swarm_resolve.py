"""Offline swarm puzzle resolver. No live LND."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_bitcoin.nostr.resolve import (
    DEFAULT_FEE_SATS_ANSWER,
    check_solved,
    fee_sats_expected,
    fee_sats_problem,
    pick_first_correct,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "agent-to-merchant-pay.py"


def test_fee_sats_141_times_4_is_564() -> None:
    assert fee_sats_expected(141, 4) == 564
    assert fee_sats_expected(141, 4) == DEFAULT_FEE_SATS_ANSWER
    problem = fee_sats_problem(141, 4)
    assert "ceil(vsize * sat_vb)" in problem["text"]
    assert problem["vsize"] == 141
    assert problem["sat_vb"] == 4


def test_check_solved_wrong_answer_loses() -> None:
    problem = fee_sats_problem(141, 4)
    good = {
        "type": "solved",
        "puzzle_type": "fee-sats",
        "vsize": 141,
        "sat_vb": 4,
        "answer": 564,
    }
    bad = {**good, "answer": 563}
    assert check_solved(good, problem) is True
    assert check_solved(bad, problem) is False
    assert check_solved({**good, "vsize": 140}, problem) is False


def test_pick_first_correct_ignores_wrong_then_takes_right() -> None:
    problem = fee_sats_problem(141, 4)
    wrong = {
        "type": "solved",
        "puzzle_type": "fee-sats",
        "vsize": 141,
        "sat_vb": 4,
        "answer": 1,
    }
    right = {**wrong, "answer": 564}
    winner = pick_first_correct(
        [
            (2.0, "npub1zzz", wrong),
            (3.0, "npub1aaa", right),
        ],
        problem,
    )
    assert winner == "npub1aaa"


def test_pick_first_correct_earlier_mtime_wins() -> None:
    problem = fee_sats_problem(141, 4)
    payload = {
        "type": "solved",
        "puzzle_type": "fee-sats",
        "vsize": 141,
        "sat_vb": 4,
        "answer": 564,
    }
    winner = pick_first_correct(
        [
            (5.0, "npub1zzz", payload),
            (1.0, "npub1aaa", payload),
        ],
        problem,
    )
    assert winner == "npub1aaa"


def test_hash_cli_still_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "both",
            "--offline-bus",
            "--no-llm",
            "--force-new-keys",
            "--dir",
            str(tmp_path),
            "--timeout",
            "15",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "paid=True" in out
    assert not (tmp_path / "bus").exists()


def test_puzzle_cli_offline_one_pay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "both",
            "--resolve",
            "puzzle",
            "--puzzle-type",
            "fee-sats",
            "--vsize",
            "141",
            "--sat-vb",
            "4",
            "--offline-bus",
            "--no-llm",
            "--force-new-keys",
            "--dir",
            str(tmp_path),
            "--timeout",
            "15",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert out.count("[l402] --offline-bus mock GET") == 1
    assert "paid=True" in out
    assert "create_client" not in out
    assert not (tmp_path / "bus").exists()
