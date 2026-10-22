"""GET /paid/bitcoin/btc-mining-info. Mock getmininginfo."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_mining_info as mine
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-mining-info"
_CHAIN = "regtest"
_WARN = "do-not-return-this-warning"


class _Caller:
    def __init__(self, info: object) -> None:
        self.info = info
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "getmininginfo":
            return self.info
        raise AssertionError(method)


def _info(**overrides: object) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "blocks": 100,
        "difficulty": 1,
        "networkhashps": 0,
        "pooledtx": 3,
        "chain": _CHAIN,
        "warnings": _WARN,
        "currentblockweight": 4000,
        "currentblocktx": 2,
    }
    raw.update(overrides)
    return raw


def test_mining_keeps_the_listed_fields() -> None:
    caller = _Caller(_info())
    out = mine.handle_request(caller)
    assert out == {
        "blocks": 100,
        "difficulty": 1,
        "networkhashps": 0,
        "pooledtx": 3,
    }
    assert isinstance(out["difficulty"], int)
    assert caller.calls == [("getmininginfo", [])]
    dumped = json.dumps(out)
    assert _CHAIN not in dumped
    assert _WARN not in dumped
    assert "currentblock" not in dumped


def test_bad_difficulty_or_hashrate() -> None:
    difficulty = _Caller(_info(difficulty=True))
    with pytest.raises(mine.BitcoindUnavailable):
        mine.handle_request(difficulty)
    hashrate = _Caller(_info(networkhashps=-1))
    with pytest.raises(mine.BitcoindUnavailable):
        mine.handle_request(hashrate)


def test_large_integral_hashrate_stays_an_int() -> None:
    rate = 10**21
    caller = _Caller(_info(networkhashps=Decimal(rate)))
    out = mine.handle_request(caller)
    assert out["networkhashps"] == rate
    assert type(out["networkhashps"]) is int


def test_rpc_error_hides_text() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        return mine._result_from_message(
            {"error": {"code": -1, "message": "mining failed SECRET"}, "result": None}
        )

    calls: list[tuple[str, list[Any]]] = []
    with pytest.raises(mine.BitcoindUnavailable) as raised:
        mine.handle_request(caller)
    assert calls == [("getmininginfo", [])]
    assert str(raised.value) == "bitcoind unavailable"
    assert "SECRET" not in str(raised.value)


def test_transport_error_hides_secret() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        raise OSError("password=supersecret")

    with pytest.raises(mine.BitcoindUnavailable) as raised:
        mine.handle_request(caller)
    assert str(raised.value) == "bitcoind unavailable"
    assert "password=" not in str(raised.value)


def test_allowlist() -> None:
    mine._allow("getmininginfo", [])
    with pytest.raises(mine.BitcoindUnavailable):
        mine._allow("getnetworkhashps", [])
    with pytest.raises(mine.BitcoindUnavailable):
        mine._allow("listunspent", [])
    with pytest.raises(mine.BitcoindUnavailable):
        mine._allow("getmininginfo", [120])


def test_dispatch_returns_mining(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = _Caller(_info())
    monkeypatch.setattr(mine, "_rpc_from_env", lambda: caller)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 200
    assert content_type == "application/json"
    body = json.loads(raw)
    assert body["blocks"] == 100
    assert body["difficulty"] == 1
    assert caller.calls == [("getmininginfo", [])]


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(mine, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise mine.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(mine, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    previous = 'pathregexp: "^/paid/bitcoin/btc-deployment-info$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-mining-info$"'
    demo = 'name: "l402-demo"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-mining-info"' in text
        assert text.index(previous) < text.index(needle) < text.index(demo)
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-mining-info"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_mining_info.py" in dockerfile
