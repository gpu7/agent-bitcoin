#!/usr/bin/env python3
"""Phase A Nostr agent identity PoC — no LND dependency.

Two conceptual agents (Alice, Bob):
  1. Generate secp256k1 keypairs (CSPRNG via pynostr / underlying crypto)
  2. Encrypt nsec at rest with a passphrase (Fernet + PBKDF2)
  3. Publish kind-0 profiles and a kind-1 coordination note
  4. Subscribe and verify Bob can see Alice's signed note

This does NOT pay, open channels, or call the agent-bitcoin Lightning client.

Usage (from repo root):
  uv sync --extra nostr
  export NOSTR_PASSPHRASE='choose-a-strong-passphrase'
  uv run python examples/nostr_agent_poc.py

See docs/nostr-agent-identity.md
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

# Optional dependency: pynostr
try:
    from pynostr.event import Event, EventKind
    from pynostr.filters import Filters, FiltersList
    from pynostr.key import PrivateKey
    from pynostr.relay_manager import RelayManager
except ImportError as e:  # pragma: no cover
    print(
        "Missing Nostr dependency. Install with:\n"
        "  uv sync --extra nostr\n"
        "  # or: pip install 'pynostr[websocket-client]'\n"
        f"Import error: {e}",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as e:  # pragma: no cover
    print(
        "Missing cryptography (usually pulled in with pynostr/coincurve stack).\n"
        f"Import error: {e}",
        file=sys.stderr,
    )
    sys.exit(1)

DEFAULT_RELAY = os.environ.get("NOSTR_RELAY", "wss://relay.damus.io")
DEFAULT_DIR = Path(os.environ.get("NOSTR_POC_DIR", ".nostr-poc")).resolve()
DEFAULT_PASSPHRASE = os.environ.get("NOSTR_PASSPHRASE", "")
COORD_TAG = "agent-bitcoin-nostr-poc"


def _derive_fernet_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def encrypt_nsec(nsec_hex: str, passphrase: str) -> dict:
    salt = os.urandom(16)
    f = Fernet(_derive_fernet_key(passphrase, salt))
    token = f.encrypt(nsec_hex.encode("utf-8")).decode("ascii")
    return {
        "version": 1,
        "kdf": "pbkdf2-sha256",
        "iterations": 480_000,
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "ciphertext_b64": token,
    }


def decrypt_nsec(blob: dict, passphrase: str) -> str:
    salt = base64.b64decode(blob["salt_b64"])
    f = Fernet(_derive_fernet_key(passphrase, salt))
    try:
        return f.decrypt(blob["ciphertext_b64"].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise SystemExit("Invalid passphrase or corrupt key file.") from exc


def agent_paths(root: Path, name: str) -> tuple[Path, Path]:
    return root / f"{name}.enc.json", root / f"{name}.pub.json"


def load_or_create_agent(
    root: Path, name: str, passphrase: str, force_new: bool
) -> PrivateKey:
    enc_path, pub_path = agent_paths(root, name)
    root.mkdir(parents=True, exist_ok=True)

    if enc_path.exists() and not force_new:
        blob = json.loads(enc_path.read_text(encoding="utf-8"))
        sk_hex = decrypt_nsec(blob, passphrase)
        sk = PrivateKey(bytes.fromhex(sk_hex))
        print(f"[{name}] loaded encrypted key from {enc_path}")
    else:
        sk = PrivateKey()  # CSPRNG-backed in library
        blob = encrypt_nsec(sk.hex(), passphrase)
        enc_path.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")
        os.chmod(enc_path, 0o600)
        pub_meta = {
            "name": name,
            "npub": sk.public_key.bech32(),
            "pubkey_hex": sk.public_key.hex(),
            "created_unix": int(time.time()),
            "note": "Public metadata only — never commit nsec or weak-passphrase blobs.",
        }
        pub_path.write_text(json.dumps(pub_meta, indent=2) + "\n", encoding="utf-8")
        print(f"[{name}] generated NEW keypair; encrypted nsec -> {enc_path}")

    print(f"[{name}] npub={sk.public_key.bech32()}")
    print(f"[{name}] hex ={sk.public_key.hex()}")
    return sk


def publish_profile(sk: PrivateKey, name: str, about: str) -> Event:
    content = json.dumps(
        {
            "name": name,
            "about": about,
            "agent_bitcoin_poc": True,
        }
    )
    # Kind 0 metadata
    event = Event(content, kind=EventKind.SET_METADATA)
    event.sign(sk.hex())
    return event


def publish_coord_note(sk: PrivateKey, to_pubkey_hex: str, message: str) -> Event:
    # Kind 1 text note with tags for filtering (public on relays — no secrets)
    event = Event(
        content=message,
        kind=EventKind.TEXT_NOTE,
        tags=[
            ["t", COORD_TAG],
            ["p", to_pubkey_hex],
            ["client", "agent-bitcoin-nostr-poc"],
        ],
    )
    event.sign(sk.hex())
    return event


def _drain_ok(relay_manager: RelayManager) -> None:
    while relay_manager.message_pool.has_ok_notices():
        ok = relay_manager.message_pool.get_ok_notice()
        print(f"[relay] OK/notice: {ok}")


def _drain_matching_events(
    relay_manager: RelayManager, alice_hex: str, nonce: str
) -> bool:
    found = False
    while relay_manager.message_pool.has_events():
        msg = relay_manager.message_pool.get_event()
        ev = msg.event
        print(f"[bob] received event kind={ev.kind} id={ev.id} from={ev.pubkey[:16]}…")
        if ev.pubkey == alice_hex and nonce in (ev.content or ""):
            found = True
            print(f"[bob] SUCCESS: matched Alice's note:\n  {ev.content}")
            if hasattr(ev, "verify") and not ev.verify():
                print("[bob] WARNING: event signature verify() returned False")
            else:
                print("[bob] signature OK (or verify N/A)")
    return found


def run_offline_crypto_check(alice: PrivateKey, bob: PrivateKey) -> bool:
    """Prove key ownership + signed events without any relay (always available)."""
    print("\n--- offline crypto check (no relay) ---")
    nonce = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    note = publish_coord_note(
        alice,
        bob.public_key.hex(),
        f"[agent-bitcoin-poc] offline | nonce={nonce}",
    )
    if note.pubkey != alice.public_key.hex():
        print("[offline] FAIL: event pubkey mismatch")
        return False
    if not note.verify():
        print("[offline] FAIL: signature verify failed")
        return False
    if nonce not in note.content:
        print("[offline] FAIL: content mismatch")
        return False
    print(f"[offline] PASS: Alice signed note id={note.id}")
    print(
        f"[offline] Bob would accept this event from npub={alice.public_key.bech32()}"
    )
    return True


def run_relay_roundtrip(
    relay_url: str,
    alice: PrivateKey,
    bob: PrivateKey,
    timeout: float,
) -> bool:
    """Alice publishes profile + note; Bob fetches Alice's note from the relay."""
    t = max(timeout, 5.0)
    relay_manager = RelayManager(timeout=t)
    relay_manager.add_relay(relay_url)

    author_filters = FiltersList(
        [
            Filters(
                authors=[alice.public_key.hex()],
                kinds=[EventKind.TEXT_NOTE],
                limit=20,
            )
        ]
    )
    sub_authors = uuid.uuid4().hex
    relay_manager.add_subscription_on_all_relays(sub_authors, author_filters)

    alice_profile = publish_profile(
        alice,
        "alice-agent",
        "agent-bitcoin Phase A PoC — Alice (coordination only, no LND)",
    )
    bob_profile = publish_profile(
        bob,
        "bob-agent",
        "agent-bitcoin Phase A PoC — Bob (coordination only, no LND)",
    )
    relay_manager.publish_event(alice_profile)
    relay_manager.publish_event(bob_profile)

    nonce = hashlib.sha256(os.urandom(16)).hexdigest()[:12]
    body = (
        f"[agent-bitcoin-poc] hello from Alice to Bob | nonce={nonce} | tag={COORD_TAG}"
    )
    note = publish_coord_note(alice, bob.public_key.hex(), body)
    print(f"[alice] publishing kind-1 note id={note.id}")
    relay_manager.publish_event(note)

    # Sync publish + first event delivery
    relay_manager.run_sync()
    _drain_ok(relay_manager)
    found = _drain_matching_events(relay_manager, alice.public_key.hex(), nonce)

    # Wait and poll again (relay store lag)
    if not found:
        time.sleep(min(t, 4.0))
        relay_manager.run_sync()
        _drain_ok(relay_manager)
        found = _drain_matching_events(relay_manager, alice.public_key.hex(), nonce)

    # Explicit id query (most reliable once OK accepted the event)
    if not found and note.id:
        print(f"[bob] re-query by event id={note.id}")
        try:
            relay_manager.close_all_relay_connections()
        except Exception:
            pass
        relay_manager = RelayManager(timeout=t)
        relay_manager.add_relay(relay_url)
        id_filters = FiltersList([Filters(ids=[note.id], limit=5)])
        relay_manager.add_subscription_on_all_relays(uuid.uuid4().hex, id_filters)
        relay_manager.run_sync()
        time.sleep(2.0)
        relay_manager.run_sync()
        _drain_ok(relay_manager)
        found = _drain_matching_events(relay_manager, alice.public_key.hex(), nonce)

    try:
        relay_manager.close_all_relay_connections()
    except Exception:
        pass

    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase A: two Nostr agent identities + signed note over a relay (no LND)."
    )
    parser.add_argument(
        "--relay",
        default=DEFAULT_RELAY,
        help=f"Relay WebSocket URL (default: {DEFAULT_RELAY} or NOSTR_RELAY)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"Directory for encrypted keys (default: {DEFAULT_DIR} or NOSTR_POC_DIR)",
    )
    parser.add_argument(
        "--passphrase",
        default=DEFAULT_PASSPHRASE,
        help="Passphrase for encrypting nsec (or set NOSTR_PASSPHRASE)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Relay timeout seconds (default: 8)",
    )
    parser.add_argument(
        "--force-new-keys",
        action="store_true",
        help="Regenerate Alice/Bob keys even if encrypted files exist",
    )
    parser.add_argument(
        "--keys-only",
        action="store_true",
        help="Only generate/load encrypted keys; do not talk to relays",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip relays; only prove local keygen + sign + verify (always runnable)",
    )
    parser.add_argument(
        "--skip-relay",
        action="store_true",
        help="Alias for --offline",
    )
    args = parser.parse_args()

    if not args.passphrase:
        print(
            "ERROR: Set a passphrase via --passphrase or NOSTR_PASSPHRASE.\n"
            "Example: export NOSTR_PASSPHRASE='choose-a-strong-passphrase'",
            file=sys.stderr,
        )
        return 2

    if args.passphrase in {"password", "passphrase", "secret", "test"}:
        print(
            "WARNING: weak passphrase; fine for throwaway PoC only.",
            file=sys.stderr,
        )

    print("=== agent-bitcoin Nostr Phase A PoC ===")
    print(f"key dir: {args.dir}")
    print(f"relay:   {args.relay}")
    print("LND:     not used in Phase A\n")

    alice = load_or_create_agent(
        args.dir, "alice", args.passphrase, args.force_new_keys
    )
    bob = load_or_create_agent(args.dir, "bob", args.passphrase, args.force_new_keys)

    if args.keys_only:
        print("\n--keys-only: done (no relay traffic).")
        return 0

    offline_ok = run_offline_crypto_check(alice, bob)
    if args.offline or args.skip_relay:
        if offline_ok:
            print("\nRESULT: PASS — offline crypto (Phase A minimum).")
            return 0
        print("\nRESULT: FAIL — offline crypto check.", file=sys.stderr)
        return 1

    print("\n--- relay round-trip (Alice -> Bob) ---")
    try:
        relay_ok = run_relay_roundtrip(args.relay, alice, bob, args.timeout)
    except Exception as exc:
        print(f"[relay] error: {exc}", file=sys.stderr)
        relay_ok = False

    if relay_ok:
        print(
            "\nRESULT: PASS — offline crypto + Bob observed Alice's note via the relay."
        )
        return 0

    if offline_ok:
        print(
            "\nRESULT: PARTIAL — offline crypto PASS; relay round-trip FAIL.\n"
            "Phase A identity/signing is OK; public relay may be down or filtering.\n"
            "Hints:\n"
            "  - uv run python examples/nostr_agent_poc.py --offline\n"
            "  - Try: --relay wss://nos.lol  or  --relay wss://relay.nostr.band\n"
            "  - Increase --timeout\n"
            "  - Keys under .nostr-poc/ remain valid for re-runs",
            file=sys.stderr,
        )
        # Exit 0 for partial: PoC goal (keys + sign) met; relay is environmental
        return 0

    print("\nRESULT: FAIL — offline and relay checks failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
