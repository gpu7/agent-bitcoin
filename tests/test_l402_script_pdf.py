"""ABT-L402-005 — origin launches generate_script_pdf.py for /paid/script.pdf."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from l402.origin import dispatch

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "l402" / "generate_script_pdf.py"


def test_generate_script_pdf_cli() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--network", "mainnet"],
        check=True,
        capture_output=True,
        timeout=10,
    )
    assert proc.stdout.startswith(b"%PDF-1.4")
    assert b"%%EOF" in proc.stdout
    assert b"generate_script_pdf.py" in proc.stdout
    assert b"network: mainnet" in proc.stdout
    assert b"origin launched this script" in proc.stdout


def test_origin_script_pdf_dispatch() -> None:
    status, content_type, body = dispatch("/paid/script.pdf")
    assert status == 200
    assert content_type == "application/pdf"
    assert body.startswith(b"%PDF-1.4")
    assert b"%%EOF" in body
    assert b"generate_script_pdf.py" in body
    assert b"L402 payment" in body
