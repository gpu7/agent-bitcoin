"""NIP-17-shaped private notes (gift wrap).

Structure follows NIP-17 (rumor → seal kind 13 → wrap kind 1059).
v1 encrypts rumor/seal payloads with NIP-04 (pynostr). The published NIP
specifies NIP-44; treat this as lab-grade privacy until NIP-44 is wired.
"""

from __future__ import annotations

import json
import time
from typing import Any

from pynostr.event import Event
from pynostr.key import PrivateKey

from agent_bitcoin.nwc.crypto import decrypt_payload, encrypt_payload

KIND_SEAL = 13
KIND_WRAP = 1059
KIND_RUMOR = 14


def gift_wrap(
    sender: PrivateKey,
    recipient_pubkey: str,
    plaintext: str,
    *,
    extra_tags: list[list[str]] | None = None,
) -> dict[str, Any]:
    """Build a kind-1059 gift wrap around a private rumor."""
    rumor = {
        "pubkey": sender.public_key.hex(),
        "created_at": int(time.time()),
        "kind": KIND_RUMOR,
        "tags": extra_tags or [],
        "content": plaintext,
    }
    seal_content = encrypt_payload(
        sender.hex(), recipient_pubkey, json.dumps(rumor, separators=(",", ":"))
    )
    seal = Event(kind=KIND_SEAL, content=seal_content, tags=[])
    seal.sign(sender.hex())

    wrap_sk = PrivateKey()  # ephemeral wrapper
    wrap_payload = json.dumps(
        {
            "id": seal.id,
            "pubkey": seal.pubkey,
            "created_at": seal.created_at,
            "kind": seal.kind,
            "tags": seal.tags,
            "content": seal.content,
            "sig": seal.sig,
        },
        separators=(",", ":"),
    )
    wrap_ct = encrypt_payload(wrap_sk.hex(), recipient_pubkey, wrap_payload)
    wrap = Event(
        kind=KIND_WRAP,
        content=wrap_ct,
        tags=[["p", recipient_pubkey]],
    )
    wrap.sign(wrap_sk.hex())
    return {
        "id": wrap.id,
        "pubkey": wrap.pubkey,
        "created_at": wrap.created_at,
        "kind": wrap.kind,
        "tags": wrap.tags,
        "content": wrap.content,
        "sig": wrap.sig,
    }


def gift_unwrap(recipient: PrivateKey, wrap: dict[str, Any]) -> dict[str, Any]:
    """Decrypt wrap → seal → rumor. Returns rumor dict."""
    if int(wrap.get("kind", 0)) != KIND_WRAP:
        raise ValueError("not a kind 1059 wrap")
    sender_wrap_pk = str(wrap.get("pubkey") or "")
    seal_json = decrypt_payload(
        recipient.hex(), sender_wrap_pk, wrap.get("content") or ""
    )
    seal = json.loads(seal_json)
    if int(seal.get("kind", 0)) != KIND_SEAL:
        raise ValueError("inner event is not a seal")
    rumor_json = decrypt_payload(
        recipient.hex(), str(seal.get("pubkey") or ""), seal.get("content") or ""
    )
    rumor = json.loads(rumor_json)
    if int(rumor.get("kind", 0)) != KIND_RUMOR:
        raise ValueError("rumor kind mismatch")
    return rumor
