"""Shared helpers for Nostr Phase A/B PoCs (keys + signed events).

Not part of the public SDK API — examples only.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from pynostr.event import Event, EventKind
from pynostr.key import PrivateKey

COORD_TAG_A = "agent-bitcoin-nostr-poc"
COORD_TAG_B = "agent-bitcoin-pay-v1"


def derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_nsec(nsec_hex: str, passphrase: str) -> dict[str, Any]:
    salt = os.urandom(16)
    f = Fernet(derive_fernet_key(passphrase, salt))
    token = f.encrypt(nsec_hex.encode("utf-8")).decode("ascii")
    return {
        "version": 1,
        "kdf": "pbkdf2-sha256",
        "iterations": 480_000,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "ciphertext_b64": token,
    }


def decrypt_nsec(blob: dict[str, Any], passphrase: str) -> str:
    salt = base64.b64decode(blob["salt_b64"])
    f = Fernet(derive_fernet_key(passphrase, salt))
    try:
        return f.decrypt(blob["ciphertext_b64"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SystemExit("Invalid passphrase or corrupt key file.") from exc


def agent_paths(root: Path, name: str) -> tuple[Path, Path]:
    return root / f"{name}.enc.json", root / f"{name}.pub.json"


def load_or_create_agent(
    root: Path, name: str, passphrase: str, force_new: bool = False
) -> PrivateKey:
    enc_path, pub_path = agent_paths(root, name)
    root.mkdir(parents=True, exist_ok=True)

    if enc_path.exists() and not force_new:
        blob = json.loads(enc_path.read_text(encoding="utf-8"))
        sk = PrivateKey(bytes.fromhex(decrypt_nsec(blob, passphrase)))
        print(f"[{name}] loaded encrypted key from {enc_path}")
    else:
        sk = PrivateKey()
        enc_path.write_text(
            json.dumps(encrypt_nsec(sk.hex(), passphrase), indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(enc_path, 0o600)
        pub_path.write_text(
            json.dumps(
                {
                    "name": name,
                    "npub": sk.public_key.bech32(),
                    "pubkey_hex": sk.public_key.hex(),
                    "created_unix": int(time.time()),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[{name}] generated NEW keypair; encrypted nsec -> {enc_path}")

    print(f"[{name}] npub={sk.public_key.bech32()}")
    return sk


def sign_json_event(
    sk: PrivateKey,
    payload: dict[str, Any],
    *,
    kind: int = EventKind.TEXT_NOTE,
    tags: list[list[str]] | None = None,
) -> Event:
    event = Event(
        content=json.dumps(payload, separators=(",", ":"), sort_keys=True),
        kind=kind,
        tags=tags or [],
    )
    event.sign(sk.hex())
    return event


def event_to_dict(event: Event) -> dict[str, Any]:
    if hasattr(event, "to_dict"):
        return event.to_dict()
    return {
        "id": event.id,
        "pubkey": event.pubkey,
        "created_at": event.created_at,
        "kind": int(event.kind) if not isinstance(event.kind, int) else event.kind,
        "tags": event.tags,
        "content": event.content,
        "sig": event.sig,
    }


def event_from_dict(data: dict[str, Any]) -> Event:
    # pynostr Event construction varies by version; rebuild and verify
    event = Event(
        content=data["content"],
        kind=data["kind"],
        tags=data.get("tags") or [],
        pubkey=data.get("pubkey"),
    )
    # Force fields from wire format when present
    if data.get("id"):
        event.id = data["id"]
    if data.get("created_at"):
        event.created_at = data["created_at"]
    if data.get("sig"):
        event.sig = data["sig"]
    if data.get("pubkey"):
        event.pubkey = data["pubkey"]
    return event


def parse_payload(event: Event) -> dict[str, Any]:
    return json.loads(event.content)


def write_bus_event(bus_dir: Path, name: str, event: Event) -> Path:
    bus_dir.mkdir(parents=True, exist_ok=True)
    path = bus_dir / name
    path.write_text(json.dumps(event_to_dict(event), indent=2) + "\n", encoding="utf-8")
    print(f"[bus] wrote {path}")
    return path


def read_bus_event(path: Path) -> Event:
    data = json.loads(path.read_text(encoding="utf-8"))
    event = event_from_dict(data)
    if hasattr(event, "verify") and event.sig and not event.verify():
        raise SystemExit(f"Signature verify failed for {path}")
    return event


def latest_bus_file(bus_dir: Path, suffix: str) -> Path | None:
    if not bus_dir.is_dir():
        return None
    files = sorted(bus_dir.glob(f"*{suffix}"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None
