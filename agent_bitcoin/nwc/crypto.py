"""NIP-04 content encryption helpers for NIP-47 payloads (pynostr).

NIP-47 prefers NIP-44; v1 of agent-bitcoin NWC uses NIP-04 via pynostr for
broad compatibility and offline tests. NIP-44 can be added later without
changing URI/policy APIs.
"""

from __future__ import annotations

from pynostr.key import PrivateKey

from agent_bitcoin.nwc.errors import NWCError


def client_private_key(secret_hex: str) -> PrivateKey:
    try:
        return PrivateKey(bytes.fromhex(secret_hex))
    except Exception as e:
        raise NWCError(f"invalid NWC client secret: {e}") from e


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
