"""Nostr profile summary. Local pub files only. No nsec and no relay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l402 import nostr_profile_summary as profile
from l402.origin import dispatch

_ROUTE = "/paid/nostr/nostr-profile-summary"
_NPUB = "npub1424242424242424242424242424242424242424242424242424qamrcaj"
_OTHER = "npub1hwamhwamhwamhwamhwamhwamhwamhwamhwamhwamhwamhwamhwasxw04hu"
_NOTE = "note1424242424242424242424242424242424242424242424242424qv3q9y6"
_SHORT = "npub14242424242424242424242424g8xj7df"


def test_valid_npub_is_a_short_empty_summary(tmp_path: Path) -> None:
    out = profile.handle_request(
        json.dumps({"npub": _NPUB}).encode(),
        directory=tmp_path / "missing",
    )
    dumped = json.dumps(out)
    assert out == {
        "npub_short": f"npub1…{_NPUB[-4:]}",
        "name": "",
        "about": "",
        "nip05": "",
        "picture": "",
    }
    assert _NPUB not in dumped


def test_bad_npub_does_not_read(tmp_path: Path) -> None:
    def read_bytes(_path: Path) -> bytes:
        raise AssertionError("file read")

    samples = (
        "nsec1" + ("q" * 58),
        _NPUB[:-7] + "Q" + _NPUB[-6:],
        _NPUB[:-1] + ("p" if _NPUB[-1] != "p" else "q"),
        _NOTE,
        _SHORT,
    )
    for sample in samples:
        with pytest.raises(profile.BadNpub):
            profile.handle_request(
                json.dumps({"npub": sample}).encode(),
                directory=tmp_path,
                read_bytes=read_bytes,
            )


def test_matching_name_comes_from_bob_when_alice_differs(tmp_path: Path) -> None:
    (tmp_path / "alice.pub.json").write_text(
        json.dumps({"npub": _OTHER, "name": "alice-secret"}),
        encoding="utf-8",
    )
    (tmp_path / "bob.pub.json").write_text(
        json.dumps(
            {
                "npub": _NPUB,
                "name": "bob",
                "about": "pays invoices",
                "nip05": "bob@example.com",
            }
        ),
        encoding="utf-8",
    )
    out = profile.handle_request(
        json.dumps({"npub": _NPUB}).encode(),
        directory=tmp_path,
    )
    dumped = json.dumps(out)
    assert out["npub_short"] == f"npub1…{_NPUB[-4:]}"
    assert out["name"] == "bob"
    assert out["about"] == "pays invoices"
    assert out["nip05"] == "bob@example.com"
    assert out["picture"] == ""
    assert _NPUB not in dumped
    assert _OTHER not in dumped
    assert "alice-secret" not in dumped


def test_non_https_picture_is_blank(tmp_path: Path) -> None:
    (tmp_path / "alice.pub.json").write_text(
        json.dumps(
            {
                "npub": _NPUB,
                "name": "alice",
                "about": "bad\tabout",
                "picture": "http://example.com/a.png",
            }
        ),
        encoding="utf-8",
    )
    out = profile.handle_request(
        json.dumps({"npub": _NPUB}).encode(),
        directory=tmp_path,
    )
    assert out["name"] == "alice"
    assert out["about"] == ""
    assert out["picture"] == ""
    https = tmp_path / "bob.pub.json"
    https.write_text(
        json.dumps(
            {
                "npub": _OTHER,
                "picture": "https://user@example.com/a.png",
            }
        ),
        encoding="utf-8",
    )
    userinfo = profile.handle_request(
        json.dumps({"npub": _OTHER}).encode(),
        directory=tmp_path,
    )
    assert userinfo["picture"] == ""


def test_enc_file_is_not_opened(tmp_path: Path) -> None:
    (tmp_path / "alice.pub.json").write_text(
        json.dumps({"npub": _NPUB, "name": "alice"}),
        encoding="utf-8",
    )
    (tmp_path / "alice.enc.json").write_text("secret-nsec-material", encoding="utf-8")
    opened: list[str] = []

    def read_bytes(path: Path) -> bytes:
        opened.append(path.name)
        return path.read_bytes()

    out = profile.handle_request(
        json.dumps({"npub": _NPUB}).encode(),
        directory=tmp_path,
        read_bytes=read_bytes,
    )
    assert out["name"] == "alice"
    assert opened == ["alice.pub.json"]
    assert "secret-nsec-material" not in json.dumps(out)


def test_nsec_origin_is_400(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("file read")

    monkeypatch.setattr(profile, "_read_capped", boom)
    monkeypatch.setattr(profile, "_default_dir", lambda: tmp_path)
    status, _content_type, raw = dispatch(
        _ROUTE,
        method="POST",
        body=json.dumps({"npub": "nsec1" + ("q" * 58)}).encode(),
    )
    assert status == 400
    assert json.loads(raw) == {"ok": False, "error": "bad_npub"}


def test_get_is_405(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict:
        raise AssertionError("handler called")

    monkeypatch.setattr(profile, "handle_request", boom)
    status, _content_type, raw = dispatch(_ROUTE, method="GET")
    assert status == 405
    assert json.loads(raw) == {"ok": False, "error": "method_not_allowed"}


def test_wired() -> None:
    root = Path(__file__).resolve().parents[1]
    url = "https://agent-bitcoin.net/paid/nostr/nostr-profile-summary"
    needle = 'pathregexp: "^/paid/nostr/nostr-profile-summary$"'
    for name in (
        "aperture.mainnet.yaml",
        "aperture.regtest.yaml",
        "aperture.signet.yaml",
    ):
        text = (root / "l402" / name).read_text(encoding="utf-8")
        assert 'name: "nostr-profile-summary"' in text
        assert text.index('name: "nip05-verify"') < text.index(needle)
        assert text.index(needle) < text.index('name: "btc-address-validate"')
    script = (root / "register-402index.sh").read_text(encoding="utf-8")
    window = script[script.index(url) : script.index(url) + 500]
    assert '"nostr"' in window
    docker = (root / "l402" / "Dockerfile.origin").read_text(encoding="utf-8")
    assert "nostr_profile_summary.py" in docker
