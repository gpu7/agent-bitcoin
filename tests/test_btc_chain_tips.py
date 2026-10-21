"""GET /paid/bitcoin/btc-chain-tips. Mock getchaintips."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_chain_tips as tips
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-chain-tips"
_ACTIVE = "11" * 32
_FORK = "22" * 32
_SECRET = "secret-tip-field"


class _Caller:
    def __init__(self, rows: object) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "getchaintips":
            return self.rows
        raise AssertionError(method)


def _rows() -> list[dict[str, Any]]:
    return [
        {
            "height": 200,
            "hash": _ACTIVE,
            "branchlen": 0,
            "status": "active",
            "warning": _SECRET,
        },
        {
            "height": 190,
            "hash": _FORK.upper(),
            "branchlen": 4,
            "status": "valid-fork",
        },
    ]


def test_tips_mark_the_active_row() -> None:
    caller = _Caller(_rows())
    out = tips.handle_request(caller)
    assert out == {
        "tips": [
            {
                "height": 200,
                "hash": _ACTIVE,
                "branchlen": 0,
                "status": "active",
                "active": True,
            },
            {
                "height": 190,
                "hash": _FORK,
                "branchlen": 4,
                "status": "valid-fork",
                "active": False,
            },
        ]
    }
    assert caller.calls == [("getchaintips", [])]
    assert _SECRET not in json.dumps(out)


def test_empty_tips() -> None:
    caller = _Caller([])
    assert tips.handle_request(caller) == {"tips": []}


def test_bad_tips_are_unavailable() -> None:
    two = _Caller(
        [
            {"height": 1, "hash": _ACTIVE, "branchlen": 0, "status": "active"},
            {"height": 1, "hash": _FORK, "branchlen": 0, "status": "active"},
        ]
    )
    with pytest.raises(tips.BitcoindUnavailable):
        tips.handle_request(two)

    short = _Caller([{"height": 1, "hash": "abcd", "branchlen": 0, "status": "active"}])
    with pytest.raises(tips.BitcoindUnavailable):
        tips.handle_request(short)

    unknown = _Caller(
        [{"height": 1, "hash": _ACTIVE, "branchlen": 0, "status": "side"}]
    )
    with pytest.raises(tips.BitcoindUnavailable):
        tips.handle_request(unknown)


def test_rpc_error_hides_text() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        return tips._result_from_message(
            {"error": {"code": -1, "message": "tips failed SECRET"}, "result": None}
        )

    calls: list[tuple[str, list[Any]]] = []
    with pytest.raises(tips.BitcoindUnavailable) as raised:
        tips.handle_request(caller)
    assert calls == [("getchaintips", [])]
    assert "SECRET" not in str(raised.value)


def test_transport_error_hides_secret() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        raise OSError("password=supersecret")

    with pytest.raises(tips.BitcoindUnavailable) as raised:
        tips.handle_request(caller)
    assert "password=" not in str(raised.value)


def test_allowlist() -> None:
    tips._allow("getchaintips", [])
    with pytest.raises(tips.BitcoindUnavailable):
        tips._allow("getbestblockhash", [])
    with pytest.raises(tips.BitcoindUnavailable):
        tips._allow("listunspent", [])


def test_dispatch_returns_tips(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = _Caller(_rows())
    monkeypatch.setattr(tips, "_rpc_from_env", lambda: caller)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 200
    assert content_type == "application/json"
    body = json.loads(raw)
    assert body["tips"][0]["active"] is True
    assert body["tips"][1]["active"] is False
    assert caller.calls == [("getchaintips", [])]


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(tips, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise tips.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(tips, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    order = (
        'pathregexp: "^/paid/bitcoin/btc-deployment-info$"',
        'pathregexp: "^/paid/bitcoin/btc-mining-info$"',
        'pathregexp: "^/paid/bitcoin/btc-mempool-fees$"',
        'pathregexp: "^/paid/bitcoin/btc-chain-tips$"',
        'name: "l402-demo"',
    )
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        indexes = [text.index(piece) for piece in order]
        assert indexes == sorted(indexes)
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-chain-tips"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_chain_tips.py" in dockerfile
