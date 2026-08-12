"""NIP-44 v2 encrypted payloads (secp256k1 ECDH, HKDF, ChaCha20, HMAC-SHA256).

Spec: https://github.com/nostr-protocol/nips/blob/master/44.md
Requires coincurve + cryptography (.[nostr] extra).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
from typing import Final

from coincurve import PrivateKey as CPrivateKey
from coincurve import PublicKey
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand
from cryptography.hazmat.primitives.hmac import HMAC

from agent_bitcoin.nwc.errors import NWCError

NIP44_SALT: Final[bytes] = b"nip44-v2"
MIN_PLAINTEXT: Final[int] = 1
MAX_PLAINTEXT: Final[int] = 0xFFFFFFFF
EXTENDED_PREFIX_THRESHOLD: Final[int] = 65536
VERSION: Final[int] = 2


class NIP44Error(NWCError):
    """NIP-44 encrypt/decrypt failure."""


def calc_padded_len(unpadded_len: int) -> int:
    if unpadded_len <= 32:
        return 32
    next_power = 1 << (math.floor(math.log2(unpadded_len - 1)) + 1)
    chunk = 32 if next_power <= 256 else next_power // 8
    return int(chunk * (math.floor((unpadded_len - 1) / chunk) + 1))


def _pad(plaintext: str) -> bytes:
    unpadded = plaintext.encode("utf-8")
    n = len(unpadded)
    if n < MIN_PLAINTEXT or n > MAX_PLAINTEXT:
        raise NIP44Error("invalid plaintext length")
    if n >= EXTENDED_PREFIX_THRESHOLD:
        prefix = b"\x00\x00" + n.to_bytes(4, "big")
    else:
        prefix = n.to_bytes(2, "big")
    suffix = b"\x00" * (calc_padded_len(n) - n)
    return prefix + unpadded + suffix


def _unpad(padded: bytes) -> str:
    if len(padded) < 2:
        raise NIP44Error("invalid padding")
    first_two = int.from_bytes(padded[0:2], "big")
    if first_two == 0:
        if len(padded) < 6:
            raise NIP44Error("invalid padding")
        unpadded_len = int.from_bytes(padded[2:6], "big")
        if unpadded_len < EXTENDED_PREFIX_THRESHOLD:
            raise NIP44Error("invalid padding")
        prefix_len = 6
    else:
        unpadded_len = first_two
        prefix_len = 2
    unpadded = padded[prefix_len : prefix_len + unpadded_len]
    if (
        unpadded_len == 0
        or len(unpadded) != unpadded_len
        or len(padded) != prefix_len + calc_padded_len(unpadded_len)
    ):
        raise NIP44Error("invalid padding")
    return unpadded.decode("utf-8")


def get_conversation_key(private_key_hex: str, public_key_hex: str) -> bytes:
    """HKDF-extract over unhashed ECDH x-coordinate."""
    try:
        sk = CPrivateKey(bytes.fromhex(private_key_hex))
        pub_raw = bytes.fromhex(public_key_hex)
        if len(pub_raw) == 32:
            pub = PublicKey(b"\x02" + pub_raw)
        elif len(pub_raw) == 33:
            pub = PublicKey(pub_raw)
        else:
            raise NIP44Error("invalid public key length")
        shared = pub.multiply(sk.secret)
        shared_x = shared.point()[0].to_bytes(32, "big")
    except NIP44Error:
        raise
    except Exception as e:
        raise NIP44Error(f"ECDH failed: {e}") from e
    h = HMAC(NIP44_SALT, hashes.SHA256())
    h.update(shared_x)
    return h.finalize()


def get_message_keys(
    conversation_key: bytes, nonce: bytes
) -> tuple[bytes, bytes, bytes]:
    if len(conversation_key) != 32:
        raise NIP44Error("invalid conversation_key length")
    if len(nonce) != 32:
        raise NIP44Error("invalid nonce length")
    keys = HKDFExpand(algorithm=hashes.SHA256(), length=76, info=nonce).derive(
        conversation_key
    )
    return keys[0:32], keys[32:44], keys[44:76]


def _chacha20(key: bytes, nonce12: bytes, data: bytes) -> bytes:
    # cryptography ChaCha20: 16-byte nonce = 4-byte LE counter || 12-byte nonce
    full_nonce = (0).to_bytes(4, "little") + nonce12
    encryptor = Cipher(algorithms.ChaCha20(key, full_nonce), mode=None).encryptor()
    return encryptor.update(data) + encryptor.finalize()


def _hmac_aad(key: bytes, message: bytes, aad: bytes) -> bytes:
    if len(aad) != 32:
        raise NIP44Error("AAD associated data must be 32 bytes")
    return hmac.new(key, aad + message, hashlib.sha256).digest()


def encrypt(
    plaintext: str,
    conversation_key: bytes,
    nonce: bytes | None = None,
) -> str:
    nonce = nonce if nonce is not None else secrets.token_bytes(32)
    chacha_key, chacha_nonce, hmac_key = get_message_keys(conversation_key, nonce)
    padded = _pad(plaintext)
    ciphertext = _chacha20(chacha_key, chacha_nonce, padded)
    mac = _hmac_aad(hmac_key, ciphertext, nonce)
    raw = bytes([VERSION]) + nonce + ciphertext + mac
    return base64.b64encode(raw).decode("ascii")


def decrypt(payload: str, conversation_key: bytes) -> str:
    if not payload or payload[0] == "#":
        raise NIP44Error("unknown encryption version")
    if len(payload) < 132:
        raise NIP44Error("invalid payload size")
    try:
        data = base64.b64decode(payload, validate=False)
    except Exception as e:
        raise NIP44Error("invalid base64") from e
    if len(data) < 99:
        raise NIP44Error("invalid data size")
    if data[0] != VERSION:
        raise NIP44Error(f"unknown version {data[0]}")
    nonce = data[1:33]
    ciphertext = data[33:-32]
    mac = data[-32:]
    chacha_key, chacha_nonce, hmac_key = get_message_keys(conversation_key, nonce)
    calculated = _hmac_aad(hmac_key, ciphertext, nonce)
    if not hmac.compare_digest(calculated, mac):
        raise NIP44Error("invalid MAC")
    padded = _chacha20(chacha_key, chacha_nonce, ciphertext)
    return _unpad(padded)


def nip44_encrypt(sender_sk_hex: str, recipient_pk_hex: str, plaintext: str) -> str:
    ck = get_conversation_key(sender_sk_hex, recipient_pk_hex)
    return encrypt(plaintext, ck)


def nip44_decrypt(receiver_sk_hex: str, sender_pk_hex: str, ciphertext: str) -> str:
    ck = get_conversation_key(receiver_sk_hex, sender_pk_hex)
    return decrypt(ciphertext, ck)
