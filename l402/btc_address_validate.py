"""Local Bitcoin address check for POST /paid/finance/btc-address-validate.

Base58Check and BIP173/BIP350 only. No LND, no bitcoind, no network.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_BODY_BYTES = 512
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_GEN = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
_BECH32 = 1
_BECH32M = 0x2BC830A3
_HRP_NETWORK = {"bc": "mainnet", "tb": "testnet", "bcrt": "regtest"}
_VERSION = {
    0x00: ("mainnet", "p2pkh"),
    0x05: ("mainnet", "p2sh"),
    0x6F: ("testnet", "p2pkh"),
    0xC4: ("testnet", "p2sh"),
}


class MissingAddress(ValueError):
    """Body is not a JSON object or address is missing."""


def _invalid(reason: str) -> dict[str, Any]:
    return {
        "valid": False,
        "network": None,
        "address_type": None,
        "reason": reason,
    }


def _valid(network: str, address_type: str) -> dict[str, Any]:
    return {
        "valid": True,
        "network": network,
        "address_type": address_type,
        "reason": "",
    }


def _b58decode(text: str) -> bytes | None:
    if not text or any(char not in _B58 for char in text):
        return None
    number = 0
    for char in text:
        number = number * 58 + _B58.index(char)
    if number:
        payload = number.to_bytes((number.bit_length() + 7) // 8, "big")
    else:
        payload = b""
    pad = 0
    for char in text:
        if char != "1":
            break
        pad += 1
    return b"\x00" * pad + payload


def _base58check(address: str) -> dict[str, Any]:
    raw = _b58decode(address)
    if raw is None:
        return _invalid("bad_charset")
    if len(raw) != 25:
        return _invalid("bad_length")
    digest = hashlib.sha256(hashlib.sha256(raw[:-4]).digest()).digest()
    if digest[:4] != raw[-4:]:
        return _invalid("bad_checksum")
    found = _VERSION.get(raw[0])
    if found is None:
        return _invalid("unknown_version")
    network, address_type = found
    return _valid(network, address_type)


def _polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for index, gen in enumerate(_GEN):
            if (top >> index) & 1:
                chk ^= gen
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _checksum_kind(hrp: str, data: list[int]) -> str | None:
    const = _polymod(_hrp_expand(hrp) + data)
    if const == _BECH32:
        return "bech32"
    if const == _BECH32M:
        return "bech32m"
    return None


def _convertbits(data: list[int]) -> list[int] | None:
    acc = 0
    bits = 0
    out: list[int] = []
    for value in data:
        if value < 0 or value > 31:
            return None
        acc = ((acc << 5) | value) & 0xFFF
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xFF)
    if bits >= 5 or ((acc << (8 - bits)) & 0xFF):
        return None
    return out


def _segwit(address: str) -> dict[str, Any]:
    if any(ord(char) < 33 or ord(char) > 126 for char in address):
        return _invalid("bad_charset")
    if address.lower() != address and address.upper() != address:
        return _invalid("bad_charset")
    text = address.lower()
    separator = text.rfind("1")
    if separator < 1:
        return _invalid("bad_charset")
    if separator + 7 > len(text) or len(text) > 90:
        return _invalid("bad_length")
    hrp, data_part = text[:separator], text[separator + 1 :]
    data: list[int] = []
    for char in data_part:
        index = _B32.find(char)
        if index < 0:
            return _invalid("bad_charset")
        data.append(index)
    kind = _checksum_kind(hrp, data)
    if kind is None:
        return _invalid("bad_checksum")
    network = _HRP_NETWORK.get(hrp)
    if network is None:
        return _invalid("unknown_hrp")
    witness_version = data[0]
    if witness_version > 16:
        return _invalid("bad_witness")
    if witness_version == 0 and kind != "bech32":
        return _invalid("bad_checksum")
    if witness_version != 0 and kind != "bech32m":
        return _invalid("bad_checksum")
    program = _convertbits(data[1:-6])
    if program is None or not 2 <= len(program) <= 40:
        return _invalid("bad_witness")
    if witness_version == 0 and len(program) == 20:
        return _valid(network, "p2wpkh")
    if witness_version == 0 and len(program) == 32:
        return _valid(network, "p2wsh")
    if witness_version == 1 and len(program) == 32:
        return _valid(network, "p2tr")
    return _invalid("bad_witness")


def _bech32_shape(address: str) -> bool:
    if address.lower() != address and address.upper() != address:
        return False
    if any(ord(char) < 33 or ord(char) > 126 for char in address):
        return False
    text = address.lower()
    separator = text.rfind("1")
    if separator < 1 or separator + 7 > len(text) or len(text) > 90:
        return False
    return all(char in _B32 for char in text[separator + 1 :])


def validate(address: str) -> dict[str, Any]:
    text = address.strip()
    if not text:
        return _invalid("empty")
    if text.lower().startswith(("bc1", "tb1", "bcrt1")):
        return _segwit(text)
    base58 = _base58check(text)
    if base58["valid"] or not _bech32_shape(text):
        return base58
    return _segwit(text)


def handle_request(body: bytes) -> dict[str, Any]:
    if len(body) > MAX_BODY_BYTES:
        raise MissingAddress("too_large")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MissingAddress("bad_json") from exc
    if not isinstance(payload, dict) or "address" not in payload:
        raise MissingAddress("missing_address")
    address = payload["address"]
    if not isinstance(address, str):
        raise MissingAddress("missing_address")
    return validate(address)
