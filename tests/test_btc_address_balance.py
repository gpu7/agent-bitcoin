"""POST /paid/bitcoin/btc-address-balance. Mock scantxoutset."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_address_balance as bal
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-address-balance"
_ADDR = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
_TB = "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx"
_BCRT = "bcrt1qqqqsyqcyq5rqwzqfpg9scrgwpugpzysnard0ew"
_BASE58 = "mfWyW5fc9NUj75YAnFgoRLrjxgLDn2MMth"
_SCRIPT = "0014751e76e8199196d454941c45d1b3a323f1433bd6"
_TXID = "ab" * 32


class _Caller:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append(
            (
                method,
                [list(item) if isinstance(item, list) else item for item in params],
            )
        )
        return self.result


def _scan(amount: object) -> dict[str, Any]:
    return {
        "success": True,
        "txouts": 1,
        "height": 920000,
        "bestblock": "cd" * 32,
        "unspents": [
            {
                "txid": _TXID,
                "vout": 0,
                "scriptPubKey": _SCRIPT,
                "desc": "addr(" + _ADDR + ")#checksum",
                "amount": amount,
            }
        ],
        "total_amount": amount,
    }


def _body(address: str) -> bytes:
    return json.dumps({"address": address}).encode("utf-8")


def test_balance_drops_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    caller = _Caller(_scan(Decimal("0.00000150")))
    out = bal.handle_request(_ADDR, caller)
    assert out == {"address": _ADDR, "balance_sats": 150}
    assert "note" not in out
    assert caller.calls == [("scantxoutset", ["start", ["addr(" + _ADDR + ")"]])]
    dumped = json.dumps(out)
    assert _SCRIPT not in dumped
    assert _TXID not in dumped
    assert "bestblock" not in dumped
    assert "checksum" not in dumped


def test_zero_balance_has_note(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    caller = _Caller(_scan(Decimal("0")))
    out = bal.handle_request("  " + _ADDR + "  ", caller)
    assert out == {
        "address": _ADDR,
        "balance_sats": 0,
        "note": "no confirmed outputs",
    }
    assert caller.calls == [("scantxoutset", ["start", ["addr(" + _ADDR + ")"]])]


def test_half_up_and_decimal_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    rounded = _Caller(_scan(Decimal("0.000000015")))
    assert bal.handle_request(_ADDR, rounded)["balance_sats"] == 2
    text = _Caller(_scan("0.00000150"))
    assert bal.handle_request(_ADDR, text)["balance_sats"] == 150


def test_bad_address_does_not_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")

    def boom(method: str, params: list[Any]) -> Any:
        raise AssertionError("rpc called")

    with pytest.raises(bal.BadAddress):
        bal.handle_request("not-an-address", boom)
    with pytest.raises(bal.BadAddress):
        bal.handle_request(_TB, boom)


def test_regtest_accepts_bcrt_and_base58(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "regtest")
    for address in (_BCRT, _BASE58):
        caller = _Caller(_scan(Decimal("0")))
        out = bal.handle_request(address, caller)
        assert out["address"] == address
        assert out["balance_sats"] == 0
        assert caller.calls == [("scantxoutset", ["start", ["addr(" + address + ")"]])]
    caller = _Caller(_scan(Decimal("1")))
    with pytest.raises(bal.BadAddress):
        bal.handle_request(_ADDR, caller)
    assert caller.calls == []


def test_signet_accepts_testnet_bech32(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "signet")
    caller = _Caller(_scan(Decimal("0")))
    out = bal.handle_request(_TB, caller)
    assert out["balance_sats"] == 0
    assert caller.calls == [("scantxoutset", ["start", ["addr(" + _TB + ")"]])]


def test_unknown_chain_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "signet2")

    def boom(method: str, params: list[Any]) -> Any:
        raise AssertionError("rpc called")

    with pytest.raises(bal.BitcoindUnavailable):
        bal.handle_request(_ADDR, boom)


def test_failed_scan_and_bad_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    failed = _Caller({"success": False, "total_amount": Decimal("1")})
    with pytest.raises(bal.BitcoindUnavailable):
        bal.handle_request(_ADDR, failed)
    flagged = _Caller(_scan(True))
    with pytest.raises(bal.BitcoindUnavailable):
        bal.handle_request(_ADDR, flagged)
    shape = _Caller("not-an-object")
    with pytest.raises(bal.BitcoindUnavailable):
        bal.handle_request(_ADDR, shape)


def test_rpc_error_hides_text() -> None:
    with pytest.raises(bal.BitcoindUnavailable) as raised:
        bal._result_from_message(
            {
                "error": {"code": -1, "message": "Scan already in progress SECRET"},
                "result": None,
            }
        )
    assert str(raised.value) == "bitcoind unavailable"
    assert "SECRET" not in str(raised.value)


def test_transport_error_hides_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")

    def boom(method: str, params: list[Any]) -> Any:
        raise OSError("password=supersecret")

    with pytest.raises(bal.BitcoindUnavailable) as raised:
        bal.handle_request(_ADDR, boom)
    assert str(raised.value) == "bitcoind unavailable"
    assert "password=" not in str(raised.value)


def test_allowlist() -> None:
    bal._allow("scantxoutset", ["start", ["addr(" + _ADDR + ")"]])
    bal._allow("scantxoutset", ["abort"])
    with pytest.raises(bal.BitcoindUnavailable):
        bal._allow("listunspent", [])
    with pytest.raises(bal.BitcoindUnavailable):
        bal._allow("gettxoutsetinfo", [])
    with pytest.raises(bal.BitcoindUnavailable):
        bal._allow("sendtoaddress", [_ADDR, 1])
    with pytest.raises(bal.BitcoindUnavailable):
        bal._allow("scantxoutset", ["start", ["pkh(02aa)"]])


def test_parse_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    assert bal.parse_request(_body("  " + _ADDR + " ")) == _ADDR
    with pytest.raises(bal.MissingAddress):
        bal.parse_request(b"")
    with pytest.raises(bal.MissingAddress):
        bal.parse_request(b'{"amount": 1}')
    with pytest.raises(bal.BadAddress):
        bal.parse_request(_body("zz"))


def test_dispatch_returns_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    caller = _Caller(_scan(Decimal("0.00000150")))
    monkeypatch.setattr(bal, "_rpc_from_env", lambda: caller)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=_body(_ADDR))
    assert status == 200
    assert content_type == "application/json"
    assert json.loads(raw) == {"address": _ADDR, "balance_sats": 150}
    assert caller.calls == [("scantxoutset", ["start", ["addr(" + _ADDR + ")"]])]


@pytest.mark.parametrize(
    "body",
    [b"", b"{", b"{}", b'{"address": 1}', _body("zz").decode().encode()],
)
def test_bad_body_does_not_call_handler(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    def boom(address: str, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(bal, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=body)
    assert status == 400
    assert content_type == "application/json"
    assert json.loads(raw)["ok"] is False
    assert json.loads(raw)["error"] in {"missing_address", "bad_address"}


def test_wrong_network_does_not_call_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("L402_NETWORK", "mainnet")

    def boom(address: str, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(bal, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=_body(_TB))
    assert status == 400
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bad_address"}


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(address: str, caller: object = None) -> dict[str, object]:
        raise bal.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(bal, "handle_request", boom)
    monkeypatch.setenv("L402_NETWORK", "mainnet")
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=_body(_ADDR))
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(address: str, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(bal, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE + "?address=" + _ADDR)
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    previous = 'pathregexp: "^/paid/bitcoin/btc-tx-summary$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-address-balance$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-address-balance"' in text
        assert needle in text
        assert (
            text.index(previous) < text.index(needle) < text.index('name: "l402-demo"')
        )
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-address-balance"
    assert url in script
    window = script[script.index(url) : script.index(url) + 360]
    assert '"bitcoin"' in window
    assert '"POST"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_address_balance.py" in dockerfile
