"""Offline client-pack checks. No Docker up, no mainnet pay."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "examples" / "client-pack"
SCHEMA = json.loads((PACK / "hello.schema.json").read_text(encoding="utf-8"))


def test_setup_help() -> None:
    proc = subprocess.run(
        ["bash", str(PACK / "setup.sh"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "client-hello.json" in proc.stdout
    assert "Does not" in proc.stdout


def test_smoke_help() -> None:
    proc = subprocess.run(
        ["bash", str(PACK / "smoke-l402.sh"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "100" in proc.stdout
    assert "l402-client-lnd" in proc.stdout


def test_compose_parses() -> None:
    text = (PACK / "docker-compose.yml").read_text(encoding="utf-8")
    assert "neutrino" in text
    assert "l402-client-lnd" in text
    assert "127.0.0.1:10009:10009" in text
    assert "0.0.0.0/0" not in text
    try:
        import yaml  # type: ignore
    except ImportError:
        return
    data = yaml.safe_load(text)
    svc = data["services"]["l402-client-lnd"]
    assert svc["container_name"] == "l402-client-lnd"
    assert any("neutrino" in str(x) for x in svc["command"])


def test_hello_schema_accepts_sample() -> None:
    sample = {
        "egress_ip": "203.0.113.10",
        "identity_pubkey": "0" * 66,
        "l402_host": "http://3.90.159.146:8081",
    }
    required = SCHEMA["required"]
    for key in required:
        assert key in sample
    assert len(sample["identity_pubkey"]) == 66
    secret_keys = ("seed", "macaroon", "password", "nsec")
    for bad in secret_keys:
        assert bad not in SCHEMA["properties"]
        assert bad not in sample


def test_hello_schema_rejects_seed_field() -> None:
    assert "seed" not in SCHEMA.get("properties", {})
    assert SCHEMA.get("additionalProperties") is False
