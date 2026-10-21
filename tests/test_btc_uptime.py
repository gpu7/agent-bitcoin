"""GET /paid/bitcoin/btc-uptime. Mock uptime and getnetworkinfo."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_uptime as up
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-uptime"
_WARN = "do-not-return-this-warning"
_LOCAL = "203.0.113.5:8333"
_NET = "onion-secret-network"
_SUB = "/Satoshi:28.0.0/"


class _Caller:
    def __init__(self, uptime: object, info: object) -> None:
        self.uptime = uptime
        self.info = info
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "uptime":
            return self.uptime
        if method == "getnetworkinfo":
            return self.info
        raise AssertionError(method)


def _info(**overrides: object) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "version": 280000,
        "subversion": _SUB,
        "protocolversion": 70016,
        "connections": 8,
        "warnings": _WARN,
        "localaddresses": [{"address": _LOCAL, "port": 8333}],
        "networks": [{"name": _NET, "reachable": True, "limited": False}],
        "timeoffset": 1,
        "relayfee": Decimal("0.00001000"),
    }
    raw.update(overrides)
    return raw


def _assert_dropped(dumped: str) -> None:
    assert _WARN not in dumped
    assert _LOCAL not in dumped
    assert _NET not in dumped
    assert "0.00001000" not in dumped


def test_uptime_keeps_the_listed_fields() -> None:
    caller = _Caller(3600, _info())
    out = up.handle_request(caller)
    assert out == {
        "uptime_seconds": 3600,
        "version": 280000,
        "subversion": _SUB,
        "protocolversion": 70016,
        "connections": 8,
    }
    assert caller.calls == [("uptime", []), ("getnetworkinfo", [])]
    _assert_dropped(json.dumps(out))


def test_missing_connections_is_omitted() -> None:
    raw = _info()
    del raw["connections"]
    caller = _Caller(0, raw)
    out = up.handle_request(caller)
    assert out["uptime_seconds"] == 0
    assert "connections" not in out
    assert caller.calls == [("uptime", []), ("getnetworkinfo", [])]


def test_bad_uptime_stops_before_network_info() -> None:
    caller = _Caller(True, _info())
    with pytest.raises(up.BitcoindUnavailable):
        up.handle_request(caller)
    assert caller.calls == [("uptime", [])]


def test_bad_connections_and_subversion() -> None:
    connections = _Caller(10, _info(connections=True))
    with pytest.raises(up.BitcoindUnavailable):
        up.handle_request(connections)
    assert connections.calls == [("uptime", []), ("getnetworkinfo", [])]

    broken = "/Satoshi:\x00:28.0.0/"
    subversion = _Caller(10, _info(subversion=broken))
    with pytest.raises(up.BitcoindUnavailable):
        up.handle_request(subversion)
    assert subversion.calls == [("uptime", []), ("getnetworkinfo", [])]


def test_uptime_rpc_error_stops_and_hides_text() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        return up._result_from_message(
            {"error": {"code": -1, "message": "uptime failed SECRET"}, "result": None}
        )

    calls: list[tuple[str, list[Any]]] = []
    with pytest.raises(up.BitcoindUnavailable) as raised:
        up.handle_request(caller)
    assert calls == [("uptime", [])]
    assert str(raised.value) == "bitcoind unavailable"
    assert "SECRET" not in str(raised.value)


def test_transport_error_hides_secret() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        raise OSError("password=supersecret")

    with pytest.raises(up.BitcoindUnavailable) as raised:
        up.handle_request(caller)
    assert str(raised.value) == "bitcoind unavailable"
    assert "password=" not in str(raised.value)


def test_allowlist() -> None:
    up._allow("uptime", [])
    up._allow("getnetworkinfo", [])
    with pytest.raises(up.BitcoindUnavailable):
        up._allow("getblockchaininfo", [])
    with pytest.raises(up.BitcoindUnavailable):
        up._allow("listunspent", [])
    with pytest.raises(up.BitcoindUnavailable):
        up._allow("uptime", [1])


def test_dispatch_returns_uptime(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = _Caller(3600, _info())
    monkeypatch.setattr(up, "_rpc_from_env", lambda: caller)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 200
    assert content_type == "application/json"
    body = json.loads(raw)
    assert body["uptime_seconds"] == 3600
    assert body["version"] == 280000
    assert caller.calls == [("uptime", []), ("getnetworkinfo", [])]


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(up, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise up.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(up, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    previous = 'pathregexp: "^/paid/bitcoin/btc-address-balance$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-uptime$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-uptime"' in text
        assert needle in text
        assert (
            text.index(previous) < text.index(needle) < text.index('name: "l402-demo"')
        )
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-uptime"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_uptime.py" in dockerfile
