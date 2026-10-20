"""register-402index.sh selects one service. The curl stub never hits the network."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "register-402index.sh"


@pytest.fixture
def curl_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "calls"
    directory.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "curl"
    stub.write_text(
        "#!/bin/sh\n"
        "n=0\n"
        'if [ -f "$CURL_DIR/count" ]; then n=$(cat "$CURL_DIR/count"); fi\n'
        "n=$((n + 1))\n"
        'printf "%s\\n" "$n" > "$CURL_DIR/count"\n'
        'printf "%s\\n" "$*" > "$CURL_DIR/call-$n"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("CURL_DIR", str(directory))
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    return directory


def _calls(directory: Path) -> list[str]:
    paths = sorted(
        directory.glob("call-*"),
        key=lambda path: int(path.name.split("-", 1)[1]),
    )
    return [path.read_text(encoding="utf-8") for path in paths]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_no_argument_registers_every_service(curl_dir: Path) -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    expected = text.count("\nregister \\")
    proc = _run()
    assert proc.returncode == 0
    bodies = _calls(curl_dir)
    assert len(bodies) == expected
    joined = "\n".join(bodies)
    assert "https://agent-bitcoin.net/paid/finance/btc-usd" in joined
    assert "https://agent-bitcoin.net/paid/bitcoin/btc-network-info" in joined


def test_short_name_registers_one_service(curl_dir: Path) -> None:
    proc = _run("btc-network-info")
    assert proc.returncode == 0
    bodies = _calls(curl_dir)
    assert len(bodies) == 1
    assert "https://agent-bitcoin.net/paid/bitcoin/btc-network-info" in bodies[0]
    assert "https://agent-bitcoin.net/paid/finance/btc-usd" not in bodies[0]


def test_full_name_registers_one_service(curl_dir: Path) -> None:
    proc = _run("agent-bitcoin: btc-usd")
    assert proc.returncode == 0
    bodies = _calls(curl_dir)
    assert len(bodies) == 1
    assert "https://agent-bitcoin.net/paid/finance/btc-usd" in bodies[0]


def test_unknown_service_does_not_call_curl(curl_dir: Path) -> None:
    proc = _run("not-a-service")
    assert proc.returncode == 1
    assert "Unknown service: not-a-service" in proc.stderr
    assert _calls(curl_dir) == []


def test_two_arguments_do_not_call_curl(curl_dir: Path) -> None:
    proc = _run("btc-usd", "btc-network-info")
    assert proc.returncode == 1
    assert "Usage:" in proc.stderr
    assert _calls(curl_dir) == []
