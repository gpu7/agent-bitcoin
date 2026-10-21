"""GET /paid/bitcoin/btc-block-header. Mock getblockhash and getblockheader."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from l402 import btc_block_header as hdr
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-block-header"
_HASH = "ab" * 32
_PREV = "cd" * 32
_MERKLE = "11" * 32
_NEXT = "22" * 32


class _Caller:
    def __init__(self, header: dict[str, Any], block_hash: str = _HASH.upper()) -> None:
        self.header = header
        self.block_hash = block_hash
        self.calls: list[tuple[str, list[Any]]] = []

    def __call__(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, list(params)))
        if method == "getblockhash":
            return self.block_hash
        if method == "getblockheader":
            return self.header
        raise AssertionError(method)


def _header(**overrides: object) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "hash": _HASH.upper(),
        "height": 920000,
        "previousblockhash": _PREV.upper(),
        "time": 1_700_000_200,
        "bits": "1D00FFFF",
        "nonce": 123456,
        "version": 536870912,
        "merkleroot": _MERKLE,
        "nextblockhash": _NEXT,
        "difficulty": Decimal("9999.5"),
        "nTx": 424242,
        "confirmations": 3,
    }
    raw.update(overrides)
    return raw


def test_header_keeps_the_listed_fields() -> None:
    caller = _Caller(_header())
    out = hdr.handle_request(920000, caller)
    assert out == {
        "height": 920000,
        "hash": _HASH,
        "previousblockhash": _PREV,
        "time": 1_700_000_200,
        "bits": "1d00ffff",
        "nonce": 123456,
        "version": 536870912,
    }
    assert caller.calls == [
        ("getblockhash", [920000]),
        ("getblockheader", [_HASH, True]),
    ]
    dumped = json.dumps(out)
    assert _MERKLE not in dumped
    assert _NEXT not in dumped
    assert "9999.5" not in dumped
    assert "424242" not in dumped


def test_genesis_omits_previous_and_missing_version() -> None:
    raw = _header(height=0)
    raw.pop("previousblockhash")
    raw.pop("version")
    out = hdr.handle_request(0, _Caller(raw))
    assert "previousblockhash" not in out
    assert "version" not in out
    assert out["height"] == 0
    assert out["hash"] == _HASH


@pytest.mark.parametrize(
    ("block_hash", "patch"),
    [
        ("zz" * 32, {}),
        (_HASH, {"hash": _PREV}),
        (_HASH, {"nonce": True}),
        (_HASH, {"bits": "zzzzzzzz"}),
        (_HASH, {"bits": "abc"}),
        (_HASH, {"height": 1}),
    ],
)
def test_bad_header_is_unavailable(block_hash: str, patch: dict) -> None:
    with pytest.raises(hdr.BitcoindUnavailable):
        hdr.handle_request(920000, _Caller(_header(**patch), block_hash))


def test_rpc_code_minus_8_is_not_found() -> None:
    message = {
        "error": {"code": -8, "message": "Block height out of range secret"},
        "result": None,
    }
    with pytest.raises(hdr.BlockNotFound) as caught:
        hdr._result_from_message(message)
    assert "out of range" not in str(caught.value)
    assert "secret" not in str(caught.value)


def test_caller_not_found_hides_the_core_message() -> None:
    def boom(method: str, params: list[Any]) -> Any:
        raise hdr.BlockNotFound("Block height out of range secret")

    with pytest.raises(hdr.BlockNotFound) as caught:
        hdr.handle_request(920000, boom)
    assert "secret" not in str(caught.value)


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom(method: str, params: list[Any]) -> Any:
        raise RuntimeError("password=hidden")

    with pytest.raises(hdr.BitcoindUnavailable) as caught:
        hdr.handle_request(920000, boom)
    assert "password=hidden" not in str(caught.value)


def test_allowlist_rejects_other_methods() -> None:
    with pytest.raises(hdr.BitcoindUnavailable):
        hdr._allow("getblock", [])
    with pytest.raises(hdr.BitcoindUnavailable):
        hdr._allow("getblockheader", [_HASH, False])
    hdr._allow("getblockhash", [0])
    hdr._allow("getblockheader", [_HASH, True])


def test_dispatch_passes_height(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake(height: int, caller: object = None) -> dict[str, object]:
        seen.append(height)
        return {
            "height": height,
            "hash": _HASH,
            "time": 1,
            "bits": "1d00ffff",
            "nonce": 0,
        }

    monkeypatch.setattr(hdr, "handle_request", fake)
    status, content_type, raw = dispatch(f"{_ROUTE}?height=920000")
    assert status == 200
    assert content_type == "application/json"
    assert json.loads(raw)["height"] == 920000
    assert seen == [920000]


@pytest.mark.parametrize(
    ("path", "error"),
    [
        (_ROUTE, "missing_height"),
        (f"{_ROUTE}?", "missing_height"),
        (f"{_ROUTE}?height=-1", "bad_height"),
        (f"{_ROUTE}?height=10000001", "bad_height"),
        (f"{_ROUTE}?height=1.5", "bad_height"),
        (f"{_ROUTE}?hash={_HASH}", "bad_height"),
    ],
)
def test_bad_query_does_not_call_handler(
    monkeypatch: pytest.MonkeyPatch, path: str, error: str
) -> None:
    def boom(height: int, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(hdr, "handle_request", boom)
    status, content_type, raw = dispatch(path)
    assert status == 400
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": error}


def test_dispatch_not_found_hides_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(height: int, caller: object = None) -> dict[str, object]:
        raise hdr.BlockNotFound("Block height out of range secret")

    monkeypatch.setattr(hdr, "handle_request", boom)
    status, content_type, raw = dispatch(f"{_ROUTE}?height=920000")
    assert status == 404
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "block_not_found"}
    assert b"secret" not in raw


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(height: int, caller: object = None) -> dict[str, object]:
        raise hdr.BitcoindUnavailable("hidden rpc text")

    monkeypatch.setattr(hdr, "handle_request", boom)
    status, content_type, raw = dispatch(f"{_ROUTE}?height=1")
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden rpc text" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(height: int, caller: object = None) -> dict[str, object]:
        raise AssertionError("handler called")

    monkeypatch.setattr(hdr, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b'{"height": 1}')
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    tip = 'pathregexp: "^/paid/bitcoin/btc-block-tip$"'
    needle = 'pathregexp: "^/paid/bitcoin/btc-block-header$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-block-header"' in text
        assert needle in text
        assert text.index(tip) < text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-block-header"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"bitcoin"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_block_header.py" in dockerfile
