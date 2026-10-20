"""Local Bitcoin address check. No LND, no bitcoind, no network."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from l402.btc_address_validate import validate
from l402.origin import dispatch

_P2WPKH = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
_P2WSH = "bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3"
_P2TR = "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0"
_P2PKH = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_GEN = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)


def _post(body: bytes) -> tuple[int, dict]:
    status, content_type, raw = dispatch(
        "/paid/finance/btc-address-validate", method="POST", body=body
    )
    assert content_type == "application/json"
    return status, json.loads(raw)


def _b58encode(payload: bytes) -> str:
    digest = hashlib.sha256(hashlib.sha256(payload).digest()).digest()
    raw = payload + digest[:4]
    number = int.from_bytes(raw, "big")
    chars: list[str] = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_B58[rem])
    pad = 0
    for byte in raw:
        if byte != 0:
            break
        pad += 1
    return "1" * pad + "".join(reversed(chars))


def _polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for index, gen in enumerate(_GEN):
            if (top >> index) & 1:
                chk ^= gen
    return chk


def _segwit_addr(hrp: str, witver: int, program: bytes) -> str:
    spec = 1 if witver == 0 else 0x2BC830A3
    acc = 0
    bits = 0
    data = [witver]
    for value in program:
        acc = (acc << 8) | value
        bits += 8
        while bits >= 5:
            bits -= 5
            data.append((acc >> bits) & 31)
    if bits:
        data.append((acc << (5 - bits)) & 31)
    values = [ord(char) >> 5 for char in hrp] + [0]
    values.extend(ord(char) & 31 for char in hrp)
    polymod = _polymod(values + data + [0, 0, 0, 0, 0, 0]) ^ spec
    checksum = [(polymod >> 5 * (5 - index)) & 31 for index in range(6)]
    return hrp + "1" + "".join(_B32[part] for part in data + checksum)


def test_mainnet_bech32_p2wpkh() -> None:
    out = validate(_P2WPKH)
    assert out == {
        "valid": True,
        "network": "mainnet",
        "address_type": "p2wpkh",
        "reason": "",
    }
    assert validate(_P2WPKH.upper()) == out
    mixed = validate("Bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
    assert mixed["valid"] is False
    assert mixed["reason"] == "bad_charset"
    padded = validate(f"  {_P2PKH}  ")
    assert padded["valid"] is True
    assert padded["address_type"] == "p2pkh"
    testnet = validate("tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx")
    assert testnet["valid"] is True
    assert testnet["network"] == "testnet"
    assert testnet["address_type"] == "p2wpkh"


def test_mainnet_p2wsh_and_p2tr() -> None:
    assert validate(_P2WSH)["address_type"] == "p2wsh"
    assert validate(_P2WSH)["network"] == "mainnet"
    taproot = validate(_P2TR)
    assert taproot == {
        "valid": True,
        "network": "mainnet",
        "address_type": "p2tr",
        "reason": "",
    }


def test_legacy_p2pkh_and_constructed_versions() -> None:
    out = validate(_P2PKH)
    assert out == {
        "valid": True,
        "network": "mainnet",
        "address_type": "p2pkh",
        "reason": "",
    }
    program = bytes(range(20))
    assert validate(_b58encode(b"\x05" + program))["address_type"] == "p2sh"
    assert validate(_b58encode(b"\x05" + program))["network"] == "mainnet"
    testnet_pkh = validate(_b58encode(b"\x6f" + program))
    assert testnet_pkh["network"] == "testnet"
    assert testnet_pkh["address_type"] == "p2pkh"
    testnet_sh = validate(_b58encode(b"\xc4" + program))
    assert testnet_sh["network"] == "testnet"
    assert testnet_sh["address_type"] == "p2sh"


def test_regtest_bech32() -> None:
    address = _segwit_addr("bcrt", 0, bytes(range(20)))
    assert validate(address) == {
        "valid": True,
        "network": "regtest",
        "address_type": "p2wpkh",
        "reason": "",
    }
    known = _segwit_addr(
        "bc", 0, bytes.fromhex("751e76e8199196d454941c45d1b3a323f1433bd6")
    )
    assert known == _P2WPKH


def test_bad_checksum() -> None:
    out = validate("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5")
    assert out == {
        "valid": False,
        "network": None,
        "address_type": None,
        "reason": "bad_checksum",
    }
    legacy = validate("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNb")
    assert legacy["valid"] is False
    assert legacy["reason"] == "bad_checksum"


def test_empty_and_unknown_hrp() -> None:
    assert validate("  ")["reason"] == "empty"
    unknown = validate("tc1qw508d6qejxtdg4y5r3zarvary0c5xw7kg3g4ty")
    assert unknown["valid"] is False
    assert unknown["reason"] == "unknown_hrp"


def test_post_valid_address() -> None:
    status, body = _post(json.dumps({"address": _P2WPKH}).encode())
    assert status == 200
    assert body["valid"] is True
    assert body["network"] == "mainnet"
    assert body["address_type"] == "p2wpkh"
    assert body["reason"] == ""


def test_missing_address_is_400() -> None:
    for body in (b"{}", b"", b"[]", b'{"address": 1}', b"not-json"):
        status, payload = _post(body)
        assert status == 400
        assert payload == {"ok": False, "error": "missing_address"}


def test_get_is_405() -> None:
    status, content_type, raw = dispatch("/paid/finance/btc-address-validate")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/finance/btc-address-validate$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-address-validate"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    assert "https://agent-bitcoin.net/paid/finance/btc-address-validate" in script
    assert '"verification"' in script
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_address_validate.py" in dockerfile
