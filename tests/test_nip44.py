"""NIP-44 v2 vectors from the NIP (offline)."""

from __future__ import annotations

import pytest

pytest.importorskip("coincurve")
pytest.importorskip("cryptography")

from agent_bitcoin.nostr.nip44 import (  # noqa: E402
    calc_padded_len,
    decrypt,
    encrypt,
    get_conversation_key,
    nip44_decrypt,
    nip44_encrypt,
)


def test_conversation_key_vector() -> None:
    sec1 = "00" * 31 + "01"
    sec2 = "00" * 31 + "02"
    from coincurve import PrivateKey

    pub2 = PrivateKey(bytes.fromhex(sec2)).public_key.format(compressed=True)[1:].hex()
    ck = get_conversation_key(sec1, pub2)
    assert (
        ck.hex() == "c41c775356fd92eadc63ff5a0dc1da211b268cbea22316767095b2871ea1412d"
    )


def test_encrypt_decrypt_spec_example() -> None:
    sec1 = "00" * 31 + "01"
    sec2 = "00" * 31 + "02"
    from coincurve import PrivateKey

    pub2 = PrivateKey(bytes.fromhex(sec2)).public_key.format(compressed=True)[1:].hex()
    ck = get_conversation_key(sec1, pub2)
    nonce = bytes.fromhex("00" * 31 + "01")
    payload = encrypt("a", ck, nonce=nonce)
    assert (
        payload
        == "AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABee0G5VSK0/9YypIObAtDKfYEAjD35uVkHyB0F4DwrcNaCXlCWZKaArsGrY6M9wnuTMxWfp1RTN9Xga8no+kF5Vsb"
    )
    assert decrypt(payload, ck) == "a"
    # swap roles
    pub1 = PrivateKey(bytes.fromhex(sec1)).public_key.format(compressed=True)[1:].hex()
    ck2 = get_conversation_key(sec2, pub1)
    assert ck2 == ck
    assert decrypt(payload, ck2) == "a"


def test_roundtrip_random() -> None:
    from coincurve import PrivateKey

    a = PrivateKey()
    b = PrivateKey()
    pub_b = b.public_key.format(compressed=True)[1:].hex()
    ct = nip44_encrypt(a.to_hex(), pub_b, "hello-nip44-nwc")
    pub_a = a.public_key.format(compressed=True)[1:].hex()
    assert nip44_decrypt(b.to_hex(), pub_a, ct) == "hello-nip44-nwc"


def test_calc_padded_len_small() -> None:
    assert calc_padded_len(1) == 32
    assert calc_padded_len(32) == 32
    assert calc_padded_len(33) == 64
