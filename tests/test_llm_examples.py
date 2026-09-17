"""Offline grok/ollama example how-tos. No live xAI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
GROK = ROOT / "examples" / "grok_example.py"
OLLAMA = ROOT / "examples" / "ollama_example.py"


def test_grok_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {**os.environ}
    env.pop("XAI_API_KEY", None)
    proc = subprocess.run(
        [sys.executable, str(GROK)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0
    assert "XAI_API_KEY" in out


def test_ollama_down_fails_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    sys.path.insert(0, str(ROOT / "examples"))
    import ollama_example as oe

    class Boom:
        def invoke(self, _msgs):
            raise ConnectionError("connection refused")

    monkeypatch.setattr(oe, "ChatOllama", lambda **_k: Boom())
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    code = oe.main()
    assert code == 1


def test_grok_prints_reply(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    sys.path.insert(0, str(ROOT / "examples"))
    import grok_example as ge

    class Fake:
        def invoke(self, _msgs):
            return SimpleNamespace(content="Yes, L402 can pay without an LLM.")

    monkeypatch.setenv("XAI_API_KEY", "test-not-a-real-key")
    monkeypatch.setattr(ge, "ChatXAI", lambda **_k: Fake())
    assert ge.main() == 0
    assert "L402" in capsys.readouterr().out
