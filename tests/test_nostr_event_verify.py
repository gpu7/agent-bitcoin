"""ABT-L402-014 — nostr event-verify NIP-01 id+sig (no relay)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from coincurve import PrivateKey

from l402 import nostr_event_verify as nev
from l402.origin import dispatch

_FIXED_NOW = datetime(2026, 9, 8, 14, 30, 0, tzinfo=timezone.utc)


def _signed_event(*, content: str = "", kind: int = 1) -> dict:
    sk = PrivateKey()
    pubkey = sk.public_key.format()[1:].hex()
    created_at = 1_700_000_000
    tags: list = []
    ev_id = nev.nip01_id(pubkey, created_at, kind, tags, content)
    sig = sk.sign_schnorr(bytes.fromhex(ev_id)).hex()
    return {
        "id": ev_id,
        "pubkey": pubkey,
        "created_at": created_at,
        "kind": kind,
        "tags": tags,
        "content": content,
        "sig": sig,
    }


def _post(body: bytes) -> tuple[int, dict]:
    status, _ctype, raw = dispatch("/paid/nostr/event-verify", method="POST", body=body)
    return status, json.loads(raw)


def test_good_event_valid() -> None:
    ev = _signed_event(content="")
    out = nev.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["ok"] is True
    assert out["service"] == "nostr-event-verify"
    assert out["source"] == "local_nostr"
    assert out["ttl_s"] == 0
    assert out["valid"] is True
    assert out["reasons"] == []
    assert out["id"] == ev["id"]
    assert out["pubkey"] == ev["pubkey"]
    assert out["kind"] == 1
    assert "content" not in out
    assert "tags" not in out
    assert "sig" not in out


def test_tampered_sig() -> None:
    ev = _signed_event()
    last = "0" if ev["sig"][-1] != "0" else "1"
    ev["sig"] = ev["sig"][:-1] + last
    out = nev.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["valid"] is False
    assert "bad_sig" in out["reasons"]
    assert "content" not in out


def test_wrong_id() -> None:
    ev = _signed_event(content="a")
    ev["content"] = "b"
    out = nev.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["valid"] is False
    assert "bad_id" in out["reasons"]


def test_missing_fields_200_bad_shape() -> None:
    status, data = _post(json.dumps({"id": "aa" * 32}).encode())
    assert status == 200
    assert data["valid"] is False
    assert data["reasons"] == ["bad_shape"]
    assert data.get("id") == "aa" * 32
    assert "pubkey" not in data


def test_empty_body_400() -> None:
    status, data = _post(b"")
    assert status == 400
    assert data == {"ok": False, "error": "missing_event"}


def test_non_object_400() -> None:
    status, data = _post(b"[]")
    assert status == 400
    assert data["error"] == "missing_event"


def test_get_405() -> None:
    status, _ctype, raw = dispatch("/paid/nostr/event-verify", method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}
