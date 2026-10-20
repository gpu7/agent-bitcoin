"""Read-only LND node card. No live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import ln_node_info as info
from l402.origin import dispatch

_ROUTE = "/paid/lightning/ln-node-info"
_PUBKEY = "02" + "ab" * 32
_COMMIT = "c0ffee" * 8
_URI = "02ab@203.0.113.8:9735"


class _Reader:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    def get_info(self) -> dict:
        self.calls += 1
        return self.payload


def _getinfo() -> dict:
    return {
        "alias": "  aws-lnd  ",
        "identity_pubkey": _PUBKEY.upper(),
        "num_active_channels": "3",
        "num_peers": 4,
        "block_height": 900_000,
        "synced_to_chain": True,
        "version": "0.18.5-beta",
        "uris": [_URI],
        "color": "#3399ff",
        "commit_hash": _COMMIT,
        "chains": [{"chain": "bitcoin", "network": "mainnet"}],
        "num_inactive_channels": 1,
    }


def test_getinfo_returns_seven_fields() -> None:
    reader = _Reader(_getinfo())
    out = info.handle_request(reader)
    dumped = json.dumps(out)
    assert out == {
        "alias": "aws-lnd",
        "identity_pubkey": _PUBKEY,
        "num_active_channels": 3,
        "num_peers": 4,
        "block_height": 900_000,
        "synced_to_chain": True,
        "version": "0.18.5-beta",
    }
    assert _URI not in dumped
    assert "#3399ff" not in dumped
    assert _COMMIT not in dumped
    assert "uris" not in dumped
    assert "commit_hash" not in dumped
    assert reader.calls == 1


def test_empty_alias_is_kept() -> None:
    raw = _getinfo()
    raw["alias"] = "   "
    out = info.handle_request(_Reader(raw))
    assert out["alias"] == ""


@pytest.mark.parametrize(
    "patch",
    [
        {"alias": "aws\nlnd"},
        {"synced_to_chain": "true"},
        {"identity_pubkey": "02" + "ab" * 31},
        {"identity_pubkey": "04" + "ab" * 32},
        {"identity_pubkey": "02" + "zz" * 32},
        {"num_active_channels": True},
        {"version": "0.18.5\nbeta"},
        {"version": "   "},
    ],
)
def test_bad_field_is_unavailable(patch: dict) -> None:
    raw = _getinfo()
    raw.update(patch)
    with pytest.raises(info.LndUnavailable):
        info.handle_request(_Reader(raw))


def test_transport_error_is_unavailable() -> None:
    class Boom:
        def get_info(self) -> dict:
            raise RuntimeError("permission denied: secret path")

    with pytest.raises(info.LndUnavailable) as caught:
        info.handle_request(Boom())  # type: ignore[arg-type]
    assert "secret path" not in str(caught.value)


def test_dispatch_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise info.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(info, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE)
    assert status == 503
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_post_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(info, "handle_request", boom)
    status, content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 405
    assert content_type == "application/json"
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_named_in_aperture_and_register_script() -> None:
    root = Path(__file__).resolve().parents[1]
    channel = 'pathregexp: "^/paid/lightning/ln-channel-stats$"'
    needle = 'pathregexp: "^/paid/lightning/ln-node-info$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "ln-node-info"' in text
        assert needle in text
        assert (
            text.index(channel) < text.index(needle) < text.index('name: "l402-demo"')
        )
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    url = "https://agent-bitcoin.net/paid/lightning/ln-node-info"
    assert url in script
    window = script[script.index(url) : script.index(url) + 280]
    assert '"lightning"' in window
    dockerfile = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "ln_node_info.py" in dockerfile
    bake = (root / "docs" / "l402-aperture.md").read_text(encoding="utf-8")
    assert "uri:/lnrpc.Lightning/GetInfo" in bake
