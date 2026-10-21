"""GET /paid/bitcoin/btc-deployment-info. Mock getblockchaininfo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_deployment_info as dep
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-deployment-info"
_CHAIN = "regtest-secret-chain"


class _Caller:
    def __init__(self, info: object) -> None:
        self.info = info
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "getblockchaininfo":
            return self.info
        raise AssertionError(method)


def _info(**overrides: object) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "chain": _CHAIN,
        "blocks": 920000,
        "softforks": {
            "segwit": {"type": "buried", "active": True, "height": 481824},
            "csv": {"type": "buried", "height": 419328},
            "taproot": {
                "type": "bip9",
                "active": True,
                "height": 709632,
                "bip9": {
                    "status": "active",
                    "bit": 2,
                    "start_time": 1619222400,
                    "timeout": 1628640000,
                    "since": 709632,
                    "min_activation_height": 709632,
                    "statistics": {"period": 2016, "count": 2016},
                },
            },
            "testdummy": {
                "type": "bip9",
                "active": False,
                "bip9": {"status": "defined", "start_time": 0, "since": 0},
            },
        },
    }
    raw.update(overrides)
    return raw


def _assert_dropped(dumped: str) -> None:
    assert "statistics" not in dumped
    assert "bit" not in dumped
    assert "testdummy" not in dumped
    assert "start_time" not in dumped
    assert "csv" not in dumped
    assert _CHAIN not in dumped
    assert "920000" not in dumped


def test_active_forks_keep_name_status_and_height() -> None:
    caller = _Caller(_info())
    out = dep.handle_request(caller)
    assert out == {
        "softforks": [
            {"name": "segwit", "status": "active", "height": 481824},
            {"name": "taproot", "status": "active", "height": 709632},
        ]
    }
    assert caller.calls == [("getblockchaininfo", [])]
    _assert_dropped(json.dumps(out))


def test_warnings_string_becomes_one_element() -> None:
    caller = _Caller(_info(softforks={}, warnings="  reindex  "))
    out = dep.handle_request(caller)
    assert out == {"softforks": [], "warnings": ["reindex"]}


def test_empty_warning_string_omits_the_key() -> None:
    caller = _Caller(_info(softforks={}, warnings="   "))
    out = dep.handle_request(caller)
    assert out == {"softforks": []}
    assert "warnings" not in out


def test_warning_array_keeps_two() -> None:
    caller = _Caller(_info(softforks={}, warnings=[" first ", "second"]))
    out = dep.handle_request(caller)
    assert out["warnings"] == ["first", "second"]


def test_height_prefers_height_then_activation_then_since() -> None:
    activation = _Caller(
        _info(
            softforks={
                "taproot": {
                    "active": True,
                    "bip9": {
                        "status": "active",
                        "min_activation_height": 709632,
                        "since": 700000,
                    },
                }
            }
        )
    )
    out = dep.handle_request(activation)
    assert out["softforks"] == [
        {"name": "taproot", "status": "active", "height": 709632}
    ]

    since = _Caller(
        _info(
            softforks={
                "csv": {"active": True, "bip9": {"status": "active", "since": 419328}}
            }
        )
    )
    out = dep.handle_request(since)
    assert out["softforks"] == [{"name": "csv", "status": "active", "height": 419328}]

    buried = _Caller(_info(softforks={"segwit": {"active": True}}))
    out = dep.handle_request(buried)
    assert out["softforks"] == [{"name": "segwit", "status": "active"}]
    assert "height" not in out["softforks"][0]


def test_softfork_array_uses_the_name_field() -> None:
    caller = _Caller(
        _info(
            softforks=[
                {"name": "segwit", "active": True, "height": 481824},
                {"name": "testdummy", "active": False},
            ]
        )
    )
    out = dep.handle_request(caller)
    assert out["softforks"] == [
        {"name": "segwit", "status": "active", "height": 481824}
    ]
    assert "testdummy" not in json.dumps(out)


def test_bad_active_height_or_warning() -> None:
    active = _Caller(_info(softforks={"segwit": {"active": 1, "height": 481824}}))
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(active)

    height = _Caller(
        _info(
            softforks={
                "segwit": {
                    "active": True,
                    "height": True,
                    "bip9": {"min_activation_height": 481824},
                }
            }
        )
    )
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(height)

    other = _Caller(
        _info(
            softforks={
                "taproot": {
                    "active": True,
                    "height": 709632,
                    "bip9": {"status": "started"},
                }
            }
        )
    )
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(other)

    warning = _Caller(_info(softforks={}, warnings="node \x00 down"))
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(warning)

    entry = _Caller(_info(softforks={}, warnings=["ok", 1]))
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(entry)


def test_more_than_16_active_forks_is_unavailable() -> None:
    forks = {f"f{i}": {"active": True, "height": i} for i in range(17)}
    caller = _Caller(_info(softforks=forks))
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(caller)


def test_missing_softforks_is_unavailable() -> None:
    caller = _Caller({"blocks": 1})
    with pytest.raises(dep.BitcoindUnavailable):
        dep.handle_request(caller)
    assert caller.calls == [("getblockchaininfo", [])]


def test_rpc_error_hides_text() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        return dep._result_from_message(
            {
                "error": {"code": -1, "message": "blockchain failed SECRET"},
                "result": None,
            }
        )

    calls: list[tuple[str, list[Any]]] = []
    with pytest.raises(dep.BitcoindUnavailable) as raised:
        dep.handle_request(caller)
    assert calls == [("getblockchaininfo", [])]
    assert str(raised.value) == "bitcoind unavailable"
    assert "SECRET" not in str(raised.value)


def test_transport_error_hides_secret() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        raise OSError("password=supersecret")

    with pytest.raises(dep.BitcoindUnavailable) as raised:
        dep.handle_request(caller)
    assert str(raised.value) == "bitcoind unavailable"
    assert "password=" not in str(raised.value)


def test_allowlist() -> None:
    dep._allow("getblockchaininfo", [])
    with pytest.raises(dep.BitcoindUnavailable):
        dep._allow("getdeploymentinfo", [])
    with pytest.raises(dep.BitcoindUnavailable):
        dep._allow("listunspent", [])
    with pytest.raises(dep.BitcoindUnavailable):
        dep._allow("getblockchaininfo", [1])


def test_dispatch_returns_forks(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = _Caller(_info())
    monkeypatch.setattr(dep, "_rpc_from_env", lambda: caller)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 200
    assert content_type == "application/json"
    body = json.loads(raw)
    assert body["softforks"][0]["name"] == "segwit"
    assert caller.calls == [("getblockchaininfo", [])]


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(dep, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise dep.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(dep, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    previous = 'pathregexp: "^/paid/bitcoin/btc-uptime$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-deployment-info$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-deployment-info"' in text
        assert needle in text
        assert (
            text.index(previous) < text.index(needle) < text.index('name: "l402-demo"')
        )
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-deployment-info"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_deployment_info.py" in dockerfile
