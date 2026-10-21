"""GET /paid/bitcoin/btc-tx-summary. Mock getrawtransaction and getmempoolentry."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_tx_summary as tx
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-tx-summary"
_TXID = "ab" * 32
_OTHER = "cd" * 32
_BLOCK = "ef" * 32
_SCRIPT = "deadbeefscriptsig"
_WITNESS = "cafebabewitnessstack"
_ADDRESS = "bc1qnotreturnedaddress"
_SECRET = "No such mempool or blockchain transaction SECRET"


class _Caller:
    def __init__(
        self,
        raw: dict[str, Any],
        entry: dict[str, Any] | None = None,
        raw_error: BaseException | None = None,
        entry_error: BaseException | None = None,
    ) -> None:
        self.raw = raw
        self.entry = entry
        self.raw_error = raw_error
        self.entry_error = entry_error
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "getrawtransaction":
            if self.raw_error is not None:
                raise self.raw_error
            return self.raw
        if method == "getmempoolentry":
            if self.entry_error is not None:
                raise self.entry_error
            return self.entry
        raise AssertionError(method)


def _raw(**overrides: object) -> dict[str, Any]:
    body: dict[str, Any] = {
        "txid": _TXID.upper(),
        "hash": _OTHER,
        "vsize": 141,
        "confirmations": 0,
        "vin": [
            {"scriptSig": {"hex": _SCRIPT}, "txinwitness": [_WITNESS]},
            {"scriptSig": {"hex": "secondinputscript"}},
        ],
        "vout": [
            {
                "value": Decimal("0.5"),
                "scriptPubKey": {"address": _ADDRESS, "asm": "OP_0"},
            }
        ],
        "hex": "0200000001fullrawtransaction",
        "blockhash": _BLOCK,
        "wtxid": "11" * 32,
    }
    body.update(overrides)
    return body


def _entry(base: object = Decimal("0.00001234")) -> dict[str, Any]:
    return {
        "vsize": 141,
        "fees": {
            "base": base,
            "modified": Decimal("8.88888888"),
        },
        "depends": [_OTHER],
        "spentby": [_BLOCK],
        "wtxid": "11" * 32,
    }


def _assert_no_scripts(dumped: str) -> None:
    assert _SCRIPT not in dumped
    assert _WITNESS not in dumped
    assert _ADDRESS not in dumped
    assert _BLOCK not in dumped
    assert "8.88888888" not in dumped
    assert "fullrawtransaction" not in dumped


def test_unconfirmed_includes_mempool_fee() -> None:
    caller = _Caller(_raw(), _entry())
    out = tx.handle_request(_TXID.upper(), caller)
    assert out == {
        "txid": _TXID,
        "confirmations": 0,
        "vsize": 141,
        "input_count": 2,
        "output_count": 1,
        "fee_btc": float(Decimal("0.00001234")),
    }
    assert caller.calls == [
        ("getrawtransaction", [_TXID, True]),
        ("getmempoolentry", [_TXID]),
    ]
    _assert_no_scripts(json.dumps(out))


def test_confirmed_skips_mempool_and_omits_fee() -> None:
    caller = _Caller(_raw(confirmations=3))
    out = tx.handle_request(_TXID, caller)
    assert out["confirmations"] == 3
    assert "fee_btc" not in out
    assert caller.calls == [("getrawtransaction", [_TXID, True])]
    _assert_no_scripts(json.dumps(out))


def test_missing_confirmations_is_zero_and_asks_mempool() -> None:
    raw = _raw()
    del raw["confirmations"]
    caller = _Caller(raw, _entry(Decimal("0")))
    out = tx.handle_request(_TXID, caller)
    assert out["confirmations"] == 0
    assert out["fee_btc"] == 0
    assert type(out["fee_btc"]) is int
    assert caller.calls == [
        ("getrawtransaction", [_TXID, True]),
        ("getmempoolentry", [_TXID]),
    ]


def test_raw_code_minus_5_is_not_found_and_stops() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        return tx._result_from_message(
            {"error": {"code": -5, "message": _SECRET}, "result": None},
            method,
        )

    calls: list[tuple[str, list[Any]]] = []
    with pytest.raises(tx.TxNotFound) as raised:
        tx.handle_request(_TXID, caller)
    assert calls == [("getrawtransaction", [_TXID, True])]
    assert str(raised.value) == "tx not found"
    assert "SECRET" not in str(raised.value)


def test_mempool_code_minus_5_omits_fee() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        if method == "getrawtransaction":
            return _raw()
        return tx._result_from_message(
            {
                "error": {"code": -5, "message": "Transaction not in mempool SECRET"},
                "result": None,
            },
            method,
        )

    calls: list[tuple[str, list[Any]]] = []
    out = tx.handle_request(_TXID, caller)
    assert "fee_btc" not in out
    assert out["confirmations"] == 0
    assert calls == [
        ("getrawtransaction", [_TXID, True]),
        ("getmempoolentry", [_TXID]),
    ]
    assert "SECRET" not in json.dumps(out)


def test_other_rpc_code_is_unavailable() -> None:
    with pytest.raises(tx.BitcoindUnavailable) as raised:
        tx._result_from_message(
            {"error": {"code": -8, "message": "SECRET height"}, "result": None},
            "getrawtransaction",
        )
    assert "SECRET" not in str(raised.value)


def test_bad_vin_bool_vsize_and_bad_fee() -> None:
    vin = _Caller(_raw(vin={"scriptSig": {"hex": _SCRIPT}}))
    with pytest.raises(tx.BitcoindUnavailable):
        tx.handle_request(_TXID, vin)
    assert vin.calls == [("getrawtransaction", [_TXID, True])]

    size = _Caller(_raw(vsize=True))
    with pytest.raises(tx.BitcoindUnavailable):
        tx.handle_request(_TXID, size)
    assert size.calls == [("getrawtransaction", [_TXID, True])]

    fee = _Caller(_raw(), _entry("1e-8"))
    with pytest.raises(tx.BitcoindUnavailable) as raised:
        tx.handle_request(_TXID, fee)
    assert "1e-8" not in str(raised.value)
    assert fee.calls == [
        ("getrawtransaction", [_TXID, True]),
        ("getmempoolentry", [_TXID]),
    ]


def test_transport_error_hides_secret() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        raise OSError("password=supersecret")

    with pytest.raises(tx.BitcoindUnavailable) as raised:
        tx.handle_request(_TXID, caller)
    assert str(raised.value) == "bitcoind unavailable"
    assert "password=" not in str(raised.value)


def test_txid_mismatch_is_unavailable() -> None:
    caller = _Caller(_raw(txid=_OTHER))
    with pytest.raises(tx.BitcoindUnavailable):
        tx.handle_request(_TXID, caller)
    assert caller.calls == [("getrawtransaction", [_TXID, True])]


def test_whole_fee_is_int_and_half_up() -> None:
    whole = _Caller(_raw(), _entry(Decimal("1")))
    assert tx.handle_request(_TXID, whole)["fee_btc"] == 1
    rounded = _Caller(_raw(), _entry(Decimal("0.000000015")))
    got = tx.handle_request(_TXID, rounded)["fee_btc"]
    assert got == float(Decimal("0.00000002"))


def test_allowlist_rejects_wallet_and_verbosity_two() -> None:
    tx._allow("getrawtransaction", [_TXID, True])
    tx._allow("getmempoolentry", [_TXID])
    with pytest.raises(tx.BitcoindUnavailable):
        tx._allow("getrawtransaction", [_TXID, 2])
    with pytest.raises(tx.BitcoindUnavailable):
        tx._allow("sendrawtransaction", [_TXID])
    with pytest.raises(tx.BitcoindUnavailable):
        tx._allow("gettransaction", [_TXID])


def test_parse_txid() -> None:
    assert tx.parse_txid(f"txid={_TXID.upper()}") == _TXID
    assert tx.parse_txid(f"&txid={_TXID}&") == _TXID
    with pytest.raises(tx.MissingTxid):
        tx.parse_txid("")
    with pytest.raises(tx.BadTxid):
        tx.parse_txid("txid=zz")
    with pytest.raises(tx.BadTxid):
        tx.parse_txid(f"txid={_TXID[:-1]}")
    with pytest.raises(tx.BadTxid):
        tx.parse_txid(f"txid={_TXID}&txid={_TXID}")


def test_missing_env_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "BITCOIND_RPC_HOST",
        "BITCOIND_RPC_PORT",
        "BITCOIND_RPC_USER",
        "BITCOIND_RPC_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(tx.BitcoindUnavailable) as raised:
        tx.handle_request(_TXID)
    assert "password=" not in str(raised.value)


def test_dispatch_passes_lowercase_txid(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake(txid: str, caller: object = None) -> dict[str, object]:
        seen.append(txid)
        return {
            "txid": txid,
            "confirmations": 0,
            "vsize": 141,
            "input_count": 1,
            "output_count": 1,
        }

    monkeypatch.setattr(tx, "handle_request", fake)
    status, content_type, raw = dispatch(f"{_ROUTE}?txid={_TXID.upper()}")
    assert status == 200
    assert content_type == "application/json"
    assert json.loads(raw)["txid"] == _TXID
    assert seen == [_TXID]


@pytest.mark.parametrize(
    ("path", "error"),
    [
        (_ROUTE, "missing_txid"),
        (f"{_ROUTE}?", "missing_txid"),
        (f"{_ROUTE}?txid=zz", "bad_txid"),
        (f"{_ROUTE}?txid={_TXID[:-1]}", "bad_txid"),
        (f"{_ROUTE}?txid={_TXID}&extra=1", "bad_txid"),
    ],
)
def test_bad_query_does_not_call_handler(
    monkeypatch: pytest.MonkeyPatch, path: str, error: str
) -> None:
    def boom(txid: str, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(tx, "handle_request", boom)
    status, content_type, raw = dispatch(path)
    assert status == 400
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": error}


def test_dispatch_not_found_hides_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(txid: str, caller: object = None) -> dict[str, object]:
        raise tx.TxNotFound(_SECRET)

    monkeypatch.setattr(tx, "handle_request", boom)
    status, content_type, raw = dispatch(f"{_ROUTE}?txid={_TXID}")
    assert status == 404
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "tx_not_found"}
    assert b"SECRET" not in raw


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(txid: str, caller: object = None) -> dict[str, object]:
        raise tx.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(tx, "handle_request", boom)
    status, content_type, raw = dispatch(f"{_ROUTE}?txid={_TXID}")
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(txid: str, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(tx, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b'{"txid": "ab"}')
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    header = 'pathregexp: "^/paid/bitcoin/btc-block-header$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-tx-summary$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-tx-summary"' in text
        assert needle in text
        assert text.index(header) < text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-tx-summary"
    assert url in script
    window = script[script.index(url) : script.index(url) + 320]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_tx_summary.py" in dockerfile
