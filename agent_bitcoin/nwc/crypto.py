"""Payload encryption for NIP-47: NIP-44 v2 default, NIP-04 lab fallback."""

from __future__ import annotations

import os

from pynostr.key import PrivateKey

from agent_bitcoin.nwc.errors import NWCError

SCHEME_NIP44 = "nip44_v2"
SCHEME_NIP04 = "nip04"


def client_private_key(secret_hex: str) -> PrivateKey:
    try:
        return PrivateKey(bytes.fromhex(secret_hex))
    except Exception as e:
        raise NWCError(f"invalid NWC client secret: {e}") from e


def nip04_allowed() -> bool:
    return os.getenv("AGENT_BITCOIN_NWC_ALLOW_NIP04", "0").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }


def default_scheme() -> str:
    return SCHEME_NIP44


def nip04_encrypt(sender_sk_hex: str, recipient_pk_hex: str, plaintext: str) -> str:
    """Encrypt UTF-8 plaintext for recipient (NIP-04 ciphertext ``?iv=`` form)."""
    sk = client_private_key(sender_sk_hex)
    try:
        return sk.encrypt_message(message=plaintext, public_key_hex=recipient_pk_hex)
    except Exception as e:
        raise NWCError(f"NIP-04 encrypt failed: {e}") from e


def nip04_decrypt(receiver_sk_hex: str, sender_pk_hex: str, ciphertext: str) -> str:
    """Decrypt NIP-04 ciphertext; ``sender_pk_hex`` is the other party's pubkey."""
    sk = client_private_key(receiver_sk_hex)
    try:
        return sk.decrypt_message(
            encoded_message=ciphertext, public_key_hex=sender_pk_hex
        )
    except Exception as e:
        raise NWCError(f"NIP-04 decrypt failed: {e}") from e


def encrypt_payload(
    sender_sk_hex: str,
    recipient_pk_hex: str,
    plaintext: str,
    *,
    scheme: str | None = None,
) -> str:
    sch = (scheme or default_scheme()).strip()
    if sch == SCHEME_NIP44:
        from agent_bitcoin.nostr.nip44 import nip44_encrypt

        return nip44_encrypt(sender_sk_hex, recipient_pk_hex, plaintext)
    if sch == SCHEME_NIP04:
        return nip04_encrypt(sender_sk_hex, recipient_pk_hex, plaintext)
    raise NWCError(f"UNSUPPORTED_ENCRYPTION: {sch}")


def decrypt_payload(
    receiver_sk_hex: str,
    sender_pk_hex: str,
    ciphertext: str,
    *,
    scheme: str | None = None,
    allow_nip04: bool | None = None,
) -> str:
    sch = (scheme or default_scheme()).strip()
    if sch == SCHEME_NIP44:
        from agent_bitcoin.nostr.nip44 import nip44_decrypt

        return nip44_decrypt(receiver_sk_hex, sender_pk_hex, ciphertext)
    if sch == SCHEME_NIP04:
        if allow_nip04 is None:
            allow_nip04 = nip04_allowed()
        if not allow_nip04:
            raise NWCError("UNSUPPORTED_ENCRYPTION: nip04 disabled")
        return nip04_decrypt(receiver_sk_hex, sender_pk_hex, ciphertext)
    raise NWCError(f"UNSUPPORTED_ENCRYPTION: {sch}")


def scheme_from_event_tags(tags: list | None) -> str:
    """Read NIP-47 ``encryption`` tag; default nip44_v2 for new events."""
    for tag in tags or []:
        if isinstance(tag, (list, tuple)) and len(tag) >= 2 and tag[0] == "encryption":
            # first listed scheme
            parts = str(tag[1]).split()
            return parts[0] if parts else SCHEME_NIP44
    # Missing tag historically meant nip04 — only honor if lab fallback enabled
    return SCHEME_NIP04 if nip04_allowed() else SCHEME_NIP44
