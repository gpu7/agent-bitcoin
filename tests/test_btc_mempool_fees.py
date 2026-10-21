"""GET /paid/bitcoin/btc-mempool-fees. Mock getmempoolinfo and estimatesmartfee."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_mempool_fees as fees
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-mempool-fees"
_MIN_FEE = Decimal("0.00001000")


class _Caller:
    def __init__(self, info: object, estimates: dict[int, object]) -> None:
        self.info = info
        self.estimates = estimates
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "getmempoolinfo":
            return self.info
        if method == "estimatesmartfee":
            return self.estimates[params[0]]
        raise AssertionError(method)


def _info() -> dict[str, Any]:
    return {
        "size": 4,
        "bytes": 800,
        "usage": 1200,
        "mempoolminfee": _MIN_FEE,
        "total_fee": Decimal("0.001"),
    }


def _estimates(**overrides: object) -> dict[int, object]:
    raw: dict[int, object] = {
        1: {"feerate": _MIN_FEE, "blocks": 1},
        3: {"errors": ["Insufficient data or no feerate found"], "blocks": 3},
        6: {"feerate": Decimal("0.00002000"), "blocks": 6},
    }
    raw.update(overrides)
    return raw


def test_fees_keep_min_fee_and_available_bands() -> None:
    caller = _Caller(_info(), _estimates())
    out = fees.handle_request(caller)
    assert out["size"] == 4
    assert out["mempoolminfee"] == float(_MIN_FEE)
    assert out["fee_bands"] == [
        {"blocks": 1, "feerate_sats_per_vb": 1},
        {"blocks": 6, "feerate_sats_per_vb": 2},
    ]
    assert caller.calls == [
        ("getmempoolinfo", []),
        ("estimatesmartfee", [1]),
        ("estimatesmartfee", [3]),
        ("estimatesmartfee", [6]),
    ]
    dumped = json.dumps(out)
    assert "total_fee" not in dumped
    assert "bytes" not in dumped
    assert "Insufficient" not in dumped


def test_all_estimate_errors_omit_fee_bands() -> None:
    missing = {"errors": ["Insufficient data or no feerate found"], "blocks": 2}
    caller = _Caller(_info(), {1: missing, 3: missing, 6: missing})
    out = fees.handle_request(caller)
    assert out == {"size": 4, "mempoolminfee": float(_MIN_FEE)}
    assert "fee_bands" not in out
    assert [method for method, _params in caller.calls] == [
        "getmempoolinfo",
        "estimatesmartfee",
        "estimatesmartfee",
        "estimatesmartfee",
    ]


def test_mempool_failure_skips_estimates() -> None:
    def caller(method: str, params: list[Any]) -> Any:
        calls.append((method, list(params)))
        return fees._result_from_message(
            {"error": {"code": -1, "message": "mempool failed SECRET"}, "result": None}
        )

    calls: list[tuple[str, list[Any]]] = []
    with pytest.raises(fees.BitcoindUnavailable) as raised:
        fees.handle_request(caller)
    assert calls == [("getmempoolinfo", [])]
    assert "SECRET" not in str(raised.value)


def test_allowlist() -> None:
    fees._allow("getmempoolinfo", [])
    fees._allow("estimatesmartfee", [1])
    fees._allow("estimatesmartfee", [3])
    fees._allow("estimatesmartfee", [6])
    with pytest.raises(fees.BitcoindUnavailable):
        fees._allow("estimatesmartfee", [2])
    with pytest.raises(fees.BitcoindUnavailable):
        fees._allow("getrawmempool", [])


def test_dispatch_returns_fees(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = _Caller(_info(), _estimates())
    monkeypatch.setattr(fees, "_rpc_from_env", lambda: caller)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 200
    assert content_type == "application/json"
    body = json.loads(raw)
    assert body["size"] == 4
    assert body["fee_bands"][0]["feerate_sats_per_vb"] == 1


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(fees, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(caller: object = None) -> dict[str, object]:
        raise fees.BitcoindUnavailable("password=supersecret")

    monkeypatch.setattr(fees, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"password=" not in raw


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    previous = 'pathregexp: "^/paid/bitcoin/btc-deployment-info$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-mempool-fees$"'
    demo = 'name: "l402-demo"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-mempool-fees"' in text
        assert text.index(previous) < text.index(needle) < text.index(demo)
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-fees"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_mempool_fees.py" in dockerfile
