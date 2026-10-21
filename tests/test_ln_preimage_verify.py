"""Preimage verify. Local SHA-256. No LND."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from l402 import ln_preimage_verify as preimage
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-preimage-verify"
_PREIMAGE = "11" * 32
_HASH = hashlib.sha256(bytes.fromhex(_PREIMAGE)).hexdigest()


def test_matching_preimage_is_valid() -> None:
    body = json.dumps({"payment_hash": _HASH, "preimage": _PREIMAGE}).encode()
    out = preimage.handle_request(body)
    dumped = json.dumps(out)
    assert out == {"valid": True}
    assert _PREIMAGE not in dumped
    assert _HASH not in dumped


def test_different_hash_is_invalid() -> None:
    body = json.dumps({"payment_hash": "00" * 32, "preimage": _PREIMAGE}).encode()
    out = preimage.handle_request(body)
    assert out == {"valid": False}
    assert _PREIMAGE not in json.dumps(out)


def test_bad_length_is_400() -> None:
    body = json.dumps({"payment_hash": _HASH, "preimage": "11" * 31}).encode()
    with pytest.raises(preimage.BadInput):
        preimage.handle_request(body)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=body)
    assert status == 400
    assert json.loads(raw) == {"ok": False, "error": "bad_input"}


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(preimage, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/lightning/ln-preimage-verify"
    names = (
        "ln-preimage-verify",
        "ln-pay-check",
        "ln-node-card",
        "ln-address-resolve",
        "ln-payee-liquidity-hint",
    )
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        positions = [text.index(f'name: "{item}"') for item in names]
        assert positions == sorted(positions)
        assert text.index('name: "ln-invoice-create"') < positions[0]
        assert positions[-1] < text.index('name: "btc-fee-estimate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 400]
    assert '"lightning"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_preimage_verify.py" in docker
