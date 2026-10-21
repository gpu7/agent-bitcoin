"""Nostr node link. Public npub files only. No nsec and no live LND."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import nostr_node_link as link
from l402.origin import dispatch

_ROUTE = "/paid/nostr/nostr-node-link"
_ALICE = "npub1" + ("q" * 58)
_PUBKEY = "02" + ("ab" * 32)


class _Info:
    def __init__(
        self, payload: dict | None = None, exc: Exception | None = None
    ) -> None:
        self.payload = payload or {"identity_pubkey": _PUBKEY}
        self.exc = exc
        self.calls: list[str] = []

    def get_info(self) -> dict:
        self.calls.append("get_info")
        if self.exc:
            raise self.exc
        return self.payload


def test_matching_npub_is_linked(tmp_path: Path) -> None:
    (tmp_path / "alice.pub.json").write_text(
        json.dumps({"npub": _ALICE, "name": "alice-secret-name"}),
        encoding="utf-8",
    )
    reader = _Info()
    out = link.handle_request(
        json.dumps({"npub": _ALICE}).encode(),
        reader,
        directory=tmp_path,
    )
    dumped = json.dumps(out)
    assert out["link"] == "linked"
    assert out["npub"] == f"npub1…{_ALICE[-4:]}"
    assert out["identity_pubkey"] == f"{_PUBKEY[:8]}…{_PUBKEY[-4:]}"
    assert _ALICE not in dumped
    assert _PUBKEY not in dumped
    assert "alice-secret-name" not in dumped
    assert "nodes" not in out
    assert reader.calls == ["get_info"]


def test_nsec_is_400_and_does_not_read(tmp_path: Path) -> None:
    def read_bytes(_path: Path) -> bytes:
        raise AssertionError("file read")

    with pytest.raises(link.BadNpub):
        link.handle_request(
            json.dumps({"npub": "nsec1" + ("q" * 58)}).encode(),
            directory=tmp_path,
            read_bytes=read_bytes,
        )


def test_missing_directory_is_not_linked(tmp_path: Path) -> None:
    reader = _Info()
    out = link.handle_request(b"{}", reader, directory=tmp_path / "missing")
    assert out == {"nodes": [], "link": "not linked"}
    assert reader.calls == []


def test_enc_file_is_not_opened(tmp_path: Path) -> None:
    (tmp_path / "alice.pub.json").write_text(
        json.dumps({"npub": _ALICE}), encoding="utf-8"
    )
    (tmp_path / "alice.enc.json").write_text("secret-nsec-material", encoding="utf-8")
    opened: list[str] = []

    def read_bytes(path: Path) -> bytes:
        opened.append(path.name)
        return path.read_bytes()

    out = link.handle_request(
        json.dumps({"npub": _ALICE}).encode(),
        _Info(),
        directory=tmp_path,
        read_bytes=read_bytes,
    )
    dumped = json.dumps(out)
    assert out["link"] == "linked"
    assert opened == ["alice.pub.json"]
    assert "secret-nsec-material" not in dumped


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(link, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_origin_unavailable_is_503(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise link.LndUnavailable("hidden grpc text")

    monkeypatch.setattr(link, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="POST", body=b"{}")
    assert status == 503
    assert json.loads(raw) == {"ok": False, "error": "lnd_unavailable"}
    assert b"hidden grpc text" not in raw


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/nostr/nostr-node-link"
    needle = 'pathregexp: "^/paid/nostr/nostr-node-link$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "nostr-node-link"' in text
        assert text.index('name: "nostr-npub-decode"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-address-validate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 500]
    assert '"nostr"' in window
    assert "nostr_node_link.py" in (root / "l402" / "Dockerfile.origin").read_text()
