"""ABT-L402-015 — nostr npub-decode NIP-19 (no nsec hex, no relay I/O)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from bech32 import bech32_encode, convertbits
from coincurve import PrivateKey

from l402 import nostr_npub_decode as nd
from l402.origin import dispatch

_FIXED_NOW = datetime(2026, 9, 8, 14, 50, 0, tzinfo=timezone.utc)


def _bech32(hrp: str, raw: bytes) -> str:
    words = convertbits(raw, 8, 5)
    assert words is not None
    return bech32_encode(hrp, words)


def _tlv(typ: int, value: bytes) -> bytes:
    return bytes([typ, len(value)]) + value


def _post(body: bytes) -> tuple[int, dict]:
    status, _ctype, raw = dispatch("/paid/nostr/npub-decode", method="POST", body=body)
    return status, json.loads(raw)


def test_npub() -> None:
    pk = PrivateKey().public_key.format()[1:]
    entity = _bech32("npub", pk)
    out = nd.handle_request(json.dumps({"entity": entity}).encode(), now=_FIXED_NOW)
    assert out["valid"] is True
    assert out["type"] == "npub"
    assert out["hex"] == pk.hex()
    assert len(out["hex"]) == 64
    assert out["reasons"] == []
    assert "entity" not in out
    assert "relays" not in out


def test_note() -> None:
    evid = bytes.fromhex("ab" * 32)
    entity = _bech32("note", evid)
    out = nd.handle_request(json.dumps({"entity": entity}).encode(), now=_FIXED_NOW)
    assert out["valid"] is True
    assert out["type"] == "note"
    assert out["hex"] == evid.hex()


def test_nprofile_relays_capped() -> None:
    pk = PrivateKey().public_key.format()[1:]
    payload = _tlv(0, pk)
    for i in range(10):
        payload += _tlv(1, f"wss://r{i}.example".encode())
    payload += _tlv(1, b"not-a-url")
    entity = _bech32("nprofile", payload)
    out = nd.handle_request(json.dumps({"entity": entity}).encode(), now=_FIXED_NOW)
    assert out["valid"] is True
    assert out["type"] == "nprofile"
    assert out["hex"] == pk.hex()
    assert len(out["relays"]) == 8
    assert all(r.startswith("wss://") for r in out["relays"])


def test_nevent() -> None:
    evid = bytes.fromhex("cd" * 32)
    payload = _tlv(0, evid) + _tlv(1, b"wss://relay.example.com")
    entity = _bech32("nevent", payload)
    out = nd.handle_request(json.dumps({"entity": entity}).encode(), now=_FIXED_NOW)
    assert out["type"] == "nevent"
    assert out["hex"] == evid.hex()
    assert out["relays"] == ["wss://relay.example.com"]


def test_nsec_rejected_no_hex() -> None:
    secret = bytes.fromhex("11" * 32)
    entity = _bech32("nsec", secret)
    status, data = _post(json.dumps({"entity": entity}).encode())
    assert status == 200
    assert data["valid"] is False
    assert data["reasons"] == ["nsec_rejected"]
    assert "hex" not in data
    assert "type" not in data
    dumped = json.dumps(data)
    assert secret.hex() not in dumped
    assert "entity" not in data


def test_garbage_bad_bech32() -> None:
    out = nd.handle_request(
        json.dumps({"entity": "not-bech32"}).encode(), now=_FIXED_NOW
    )
    assert out["valid"] is False
    assert "bad_bech32" in out["reasons"]
    assert "hex" not in out


def test_missing_entity_400() -> None:
    status, data = _post(b"{}")
    assert status == 400
    assert data == {"ok": False, "error": "missing_entity"}


def test_get_405() -> None:
    status, _ctype, raw = dispatch("/paid/nostr/npub-decode", method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}
