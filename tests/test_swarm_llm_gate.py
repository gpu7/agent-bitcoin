"""Offline llm-gate: YES/NO parse, hash among YES, skip pay, missing key."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_bitcoin.nostr.negotiate import negotiate_score
from agent_bitcoin.nostr.resolve import (
    parse_force_vote,
    parse_vote_reason,
    parse_yes_no,
    pick_llm_gate_winner,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "agent-to-merchant-pay.py"


def test_parse_yes_no() -> None:
    assert parse_yes_no("YES") == "YES"
    assert parse_yes_no("yes\nmore") == "YES"
    assert parse_yes_no("YES.") == "YES"
    assert parse_yes_no("yes please") == "YES"
    assert parse_yes_no("NO") == "NO"
    assert parse_yes_no("maybe") == "NO"
    assert parse_yes_no("") == "NO"


def test_two_yes_hash_winner() -> None:
    a_npub, b_npub = "npub1aaa", "npub1zzz"
    sa = negotiate_score("aa" * 32, "deadbeefdeadbeef", 1)
    sb = negotiate_score("bb" * 32, "deadbeefdeadbeef", 1)
    winner = pick_llm_gate_winner([(a_npub, "YES", sa), (b_npub, "YES", sb)])
    expected = a_npub if sa > sb else b_npub if sb > sa else max(a_npub, b_npub)
    assert winner == expected


def test_zero_yes_no_winner() -> None:
    assert pick_llm_gate_winner([("npub1a", "NO", 1), ("npub1b", "NO", 2)]) is None


def test_one_yes_that_npub() -> None:
    assert pick_llm_gate_winner([("npub1a", "NO", 9), ("npub1b", "YES", 1)]) == "npub1b"


def test_parse_vote_reason() -> None:
    assert parse_vote_reason("NO\nfee too high") == ("NO", "fee too high")
    assert parse_vote_reason("YES\npath hint is cheap")[0] == "YES"
    assert parse_vote_reason("") == ("NO", "unparsed")
    long = "NO\n" + ("x" * 300)
    vote, reason = parse_vote_reason(long)
    assert vote == "NO"
    assert len(reason) == 200


def test_vote_payload_reason_optional() -> None:
    with_reason = {
        "type": "vote",
        "vote": "YES",
        "reason": "ok to pay 100 sats",
        "npub": "npub1a",
        "score": 1,
    }
    without = {"type": "vote", "vote": "NO", "npub": "npub1b", "score": 2}
    assert with_reason.get("reason")
    assert not without.get("reason")
    winner = pick_llm_gate_winner(
        [
            (with_reason["npub"], parse_yes_no(with_reason["vote"]), 1),
            (without["npub"], parse_yes_no(without["vote"]), 2),
        ]
    )
    assert winner == "npub1a"


def test_missing_key_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    env.pop("XAI_API_KEY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "alice",
            "--resolve",
            "llm-gate",
            "--offline-bus",
            "--dir",
            str(tmp_path),
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "XAI_API_KEY" in out


def test_parse_force_vote() -> None:
    assert parse_force_vote(None) is None
    assert parse_force_vote("") is None
    assert parse_force_vote("yes") == "YES"
    assert parse_force_vote("NO") == "NO"
    with pytest.raises(ValueError):
        parse_force_vote("maybe")


def test_cli_force_yes_one_mock_pay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "SWARM_LLM_FORCE_VOTE": "YES",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    env.pop("XAI_API_KEY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "both",
            "--resolve",
            "llm-gate",
            "--offline-bus",
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
    assert "reason=forced_test" in out
    assert out.count("[l402] --offline-bus mock GET") == 1


def test_cli_force_no_skips_pay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "SWARM_LLM_FORCE_VOTE": "NO",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    env.pop("XAI_API_KEY", None)
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "both",
            "--resolve",
            "llm-gate",
            "--offline-bus",
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
    assert "skip L402" in out or "skipped" in out.lower()
    assert "[l402] --offline-bus mock GET" not in out
