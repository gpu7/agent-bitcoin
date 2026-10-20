"""GET /paid/bitcoin/btc-peer-info. Mock getpeerinfo. No node."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import btc_peer_info as peers
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-peer-info"
_LOCAL = "198.51.100.8:8333"
_PERM = "noban,download"


def _peer(**overrides: object) -> dict:
    row = {
        "id": 7,
        "addr": "203.0.113.5:8333",
        "addrlocal": _LOCAL,
        "addrbind": _LOCAL,
        "subver": "/Satoshi:28.0.0/",
        "inbound": False,
        "bytesrecv": 999,
        "permissions": [_PERM],
    }
    row.update(overrides)
    return row


def test_counts_and_drops_local_fields() -> None:
    out = peers.handle_request(
        lambda: [
            _peer(inbound=True),
            _peer(addr="203.0.113.9:8333", subver="/Satoshi:27.0.0/", inbound=False),
        ]
    )
    assert out["num_peers"] == 2
    assert out["inbound"] == 1
    assert out["outbound"] == 1
    assert out["peers"] == [
        {"address": "203.0.113.5:8333", "subversion": "/Satoshi:28.0.0/"},
        {"address": "203.0.113.9:8333", "subversion": "/Satoshi:27.0.0/"},
    ]
    dumped = json.dumps(out)
    assert _LOCAL not in dumped
    assert "addrbind" not in dumped
    assert "bytesrecv" not in dumped
    assert _PERM not in dumped


def test_lists_at_most_eight_peers() -> None:
    rows = [_peer(addr=f"203.0.113.{index}:8333", inbound=False) for index in range(10)]
    out = peers.handle_request(lambda: rows)
    assert out["num_peers"] == 10
    assert out["inbound"] == 0
    assert out["outbound"] == 10
    assert len(out["peers"]) == 8


def test_unsafe_address_dropped_and_subversion_cut() -> None:
    long_agent = "/" + ("A" * 80) + "/"
    out = peers.handle_request(
        lambda: [
            _peer(
                addr="user:secret@203.0.113.5:8333",
                subver=long_agent,
                inbound=False,
            )
        ]
    )
    assert out["peers"] == [{"subversion": long_agent[:64]}]
    assert "secret" not in json.dumps(out)


def test_bad_inbound_flag_is_unavailable() -> None:
    with pytest.raises(peers.BitcoindUnavailable):
        peers.handle_request(lambda: [_peer(inbound="yes")])


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom() -> list:
        raise RuntimeError("password=hidden")

    with pytest.raises(peers.BitcoindUnavailable):
        peers.handle_request(boom)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise peers.BitcoindUnavailable("hidden")

    monkeypatch.setattr(peers, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("rpc")

    monkeypatch.setattr(peers, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_register_script_and_image() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/bitcoin/btc-peer-info$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-peer-info"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-peer-info"
    assert url in script
    window = script[script.index(url) : script.index(url) + 400]
    assert "bitcoin" in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_peer_info.py" in dockerfile
