"""ABT-L402-016 — nostr zap-receipt-inspect NIP-57 kind 9735 (no relay)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from bolt11 import MilliSatoshi, TagChar, Tags, encode
from bolt11.types import Bolt11
from coincurve import PrivateKey

from l402 import nostr_event_verify as nev
from l402 import nostr_zap_receipt_inspect as zri
from l402.origin import dispatch

_FIXED_NOW = datetime(2026, 9, 8, 15, 10, 0, tzinfo=timezone.utc)
_PRIV = "11" * 32
_HASH = "aa" * 32
_SECRET = "bb" * 32
_P_HEX = "32" * 32
_SENDER_HEX = "97" * 32
_EVENT_HEX = "36" * 32


def _invoice(*, amount_msat: int | None = 1_000_000) -> str:
    tags = Tags()
    tags.add(TagChar.payment_hash, _HASH)
    tags.add(TagChar.payment_secret, _SECRET)
    tags.add(TagChar.description, "zap")
    kwargs: dict = {"currency": "bc", "date": 2_000_000_000, "tags": tags}
    if amount_msat is not None:
        kwargs["amount_msat"] = MilliSatoshi(amount_msat)
    return encode(Bolt11(**kwargs), private_key=_PRIV)


def _signed_event(
    *, kind: int = 1, tags: list | None = None, content: str = ""
) -> dict:
    sk = PrivateKey()
    pubkey = sk.public_key.format()[1:].hex()
    created_at = 1_700_000_000
    tag_list: list = tags if tags is not None else []
    ev_id = nev.nip01_id(pubkey, created_at, kind, tag_list, content)
    sig = sk.sign_schnorr(bytes.fromhex(ev_id)).hex()
    return {
        "id": ev_id,
        "pubkey": pubkey,
        "created_at": created_at,
        "kind": kind,
        "tags": tag_list,
        "content": content,
        "sig": sig,
    }


def _receipt_tags(*, bolt11: str | None, include_p: bool = True) -> list:
    tags: list = []
    if include_p:
        tags.append(["p", _P_HEX])
    tags.append(["P", _SENDER_HEX])
    tags.append(["e", _EVENT_HEX])
    if bolt11 is not None:
        tags.append(["bolt11", bolt11])
    return tags


def _post(body: bytes) -> tuple[int, dict, bytes]:
    status, _ctype, raw = dispatch(
        "/paid/nostr/zap-receipt-inspect", method="POST", body=body
    )
    return status, json.loads(raw), raw


def _assert_envelope(out: dict) -> None:
    assert out["ok"] is True
    assert out["service"] == "nostr-zap-receipt-inspect"
    assert out["version"] == "v1"
    assert out["ttl_s"] == 0
    assert out["source"] == "local_nostr"
    assert out["stale"] is False
    assert "zapper_pubkey" in out
    assert "target_pubkey" in out
    assert "target_event_id" in out
    assert "amount_sats" in out
    assert "valid" not in out
    assert "content" not in out
    assert "tags" not in out
    assert "sig" not in out
    assert "preimage" not in out
    assert "bolt11" not in out


def _assert_no_leak(raw: bytes | str, *forbidden: str) -> None:
    blob = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    lower = blob.lower()
    assert "lnbc" not in lower
    assert "lntb" not in lower
    assert "nsec" not in lower
    for item in forbidden:
        assert item not in blob


def test_valid_receipt_amount_from_bolt11() -> None:
    invoice = _invoice(amount_msat=1_000_000)
    ev = _signed_event(
        kind=9735,
        tags=_receipt_tags(bolt11=invoice) + [["amount", "999999999"]],
    )
    out = zri.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    _assert_envelope(out)
    assert out["valid_event"] is True
    assert out["is_zap_receipt"] is True
    assert out["amount_sats"] == 1000
    assert out["zapper_pubkey"] == _SENDER_HEX
    assert out["target_pubkey"] == _P_HEX
    assert out["target_event_id"] == _EVENT_HEX
    assert out["reasons"] == []
    _assert_no_leak(json.dumps(out), invoice)


def test_kind_1_not_receipt() -> None:
    ev = _signed_event(kind=1)
    status, data, raw = _post(json.dumps(ev).encode())
    assert status == 200
    _assert_envelope(data)
    assert data["valid_event"] is True
    assert data["is_zap_receipt"] is False
    assert data["amount_sats"] is None
    assert data["zapper_pubkey"] is None
    assert data["target_pubkey"] is None
    assert data["target_event_id"] is None
    assert "not_kind_9735" in data["reasons"]
    _assert_no_leak(raw)


def test_bad_sig_not_receipt() -> None:
    invoice = _invoice()
    ev = _signed_event(kind=9735, tags=_receipt_tags(bolt11=invoice))
    last = "0" if ev["sig"][-1] != "0" else "1"
    ev["sig"] = ev["sig"][:-1] + last
    out = zri.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["valid_event"] is False
    assert out["is_zap_receipt"] is False
    assert "bad_sig" in out["reasons"]
    _assert_no_leak(json.dumps(out), invoice)


def test_missing_bolt11_not_receipt() -> None:
    ev = _signed_event(kind=9735, tags=_receipt_tags(bolt11=None))
    out = zri.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["valid_event"] is True
    assert out["is_zap_receipt"] is False
    assert "missing_bolt11" in out["reasons"]
    assert out["amount_sats"] is None
    assert out["target_pubkey"] == _P_HEX
    _assert_no_leak(json.dumps(out))


def test_missing_p_not_receipt() -> None:
    invoice = _invoice()
    ev = _signed_event(kind=9735, tags=_receipt_tags(bolt11=invoice, include_p=False))
    out = zri.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["valid_event"] is True
    assert out["is_zap_receipt"] is False
    assert "missing_p" in out["reasons"]
    assert out["target_pubkey"] is None
    _assert_no_leak(json.dumps(out), invoice)


def test_zero_amount_still_receipt() -> None:
    invoice = _invoice(amount_msat=None)
    ev = _signed_event(kind=9735, tags=_receipt_tags(bolt11=invoice))
    out = zri.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["valid_event"] is True
    assert out["is_zap_receipt"] is True
    assert out["amount_sats"] is None
    assert "amount_unknown" in out["reasons"]
    _assert_no_leak(json.dumps(out), invoice)


def test_garbage_bolt11_still_receipt() -> None:
    garbage = "not-an-invoice"
    ev = _signed_event(kind=9735, tags=_receipt_tags(bolt11=garbage))
    out = zri.handle_request(json.dumps(ev).encode(), now=_FIXED_NOW)
    assert out["is_zap_receipt"] is True
    assert out["amount_sats"] is None
    assert "amount_unknown" in out["reasons"]
    _assert_no_leak(json.dumps(out), garbage)


def test_empty_body_400() -> None:
    status, data, _raw = _post(b"")
    assert status == 400
    assert data == {"ok": False, "error": "missing_event"}


def test_non_object_400() -> None:
    status, data, _raw = _post(b"[]")
    assert status == 400
    assert data["error"] == "missing_event"


def test_get_405() -> None:
    status, _ctype, raw = dispatch("/paid/nostr/zap-receipt-inspect", method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_nsec_never_in_module() -> None:
    from pathlib import Path

    text = Path(zri.__file__).read_text(encoding="utf-8")
    assert "nsec" not in text.lower()
