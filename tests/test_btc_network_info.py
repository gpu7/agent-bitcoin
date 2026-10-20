"""GET /paid/bitcoin/btc-network-info. Mock getnetworkinfo. No node."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import btc_network_info as info
from l402.origin import dispatch

_ROUTE = "/paid/bitcoin/btc-network-info"
_PROXY = "user:secret@127.0.0.1:9050"


def _raw(**overrides: object) -> dict:
    body = {
        "version": 280000,
        "subversion": "/Satoshi:28.0.0/",
        "protocolversion": 70016,
        "connections": 10,
        "networks": [
            {
                "name": "ipv4",
                "limited": False,
                "reachable": True,
                "proxy": _PROXY,
            },
            {
                "name": "onion",
                "limited": True,
                "reachable": False,
                "proxy": "",
            },
        ],
        "localaddresses": [{"address": "203.0.113.5", "port": 8333}],
        "warnings": "secret-warning",
    }
    body.update(overrides)
    return body


def test_summary_drops_proxy_and_addresses() -> None:
    out = info.handle_request(lambda: _raw())
    assert out == {
        "version": 280000,
        "subversion": "/Satoshi:28.0.0/",
        "protocolversion": 70016,
        "connections": 10,
        "networks": [
            {"name": "ipv4", "reachable": True, "limited": False},
            {"name": "onion", "reachable": False, "limited": True},
        ],
    }
    dumped = json.dumps(out)
    assert _PROXY not in dumped
    assert "localaddresses" not in dumped
    assert "203.0.113.5" not in dumped
    assert "secret-warning" not in dumped


def test_filters_networks_and_cuts_subversion() -> None:
    long_agent = "/" + ("A" * 80) + "/"
    out = info.handle_request(
        lambda: _raw(
            subversion=long_agent,
            networks=[
                {"name": "ipv6", "reachable": True, "limited": False},
                {
                    "name": "secret-net",
                    "reachable": True,
                    "limited": False,
                    "proxy": _PROXY,
                },
            ],
        )
    )
    assert out["subversion"] == long_agent[:64]
    assert out["networks"] == [
        {"name": "ipv6", "reachable": True, "limited": False},
    ]
    assert _PROXY not in json.dumps(out)


def test_missing_networks_omits_the_key() -> None:
    raw = _raw()
    del raw["networks"]
    out = info.handle_request(lambda: raw)
    assert "networks" not in out
    assert out["connections"] == 10


def test_bad_connections_or_subversion_is_unavailable() -> None:
    with pytest.raises(info.BitcoindUnavailable):
        info.handle_request(lambda: _raw(connections=True))
    with pytest.raises(info.BitcoindUnavailable):
        info.handle_request(lambda: _raw(subversion="/Satoshi:\n28.0.0/"))


def test_transport_error_does_not_return_a_partial_body() -> None:
    def boom() -> dict:
        raise RuntimeError("password=hidden")

    with pytest.raises(info.BitcoindUnavailable):
        info.handle_request(boom)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise info.BitcoindUnavailable("hidden")

    monkeypatch.setattr(info, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "bitcoind_unavailable"}
    assert b"hidden" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("rpc")

    monkeypatch.setattr(info, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_register_script_and_image() -> None:
    root = Path(__file__).resolve().parents[1]
    needle = 'pathregexp: "^/paid/bitcoin/btc-network-info$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "btc-network-info"' in text
        assert needle in text
        assert text.index(needle) < text.index('name: "l402-demo"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/bitcoin/btc-network-info"
    assert url in script
    window = script[script.index(url) : script.index(url) + 400]
    assert "bitcoin" in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "btc_network_info.py" in dockerfile
