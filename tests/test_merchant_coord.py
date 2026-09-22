"""Merchant relay coordination. No public relays, no live LND."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_bitcoin.nostr.negotiate import DEFAULT_L402_URL, invoice_id_for_url

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "agent-to-merchant-pay.py"
IID = invoice_id_for_url(DEFAULT_L402_URL)


def _examples_path() -> None:
    examples = str(ROOT / "examples")
    if examples not in sys.path:
        sys.path.insert(0, examples)


def _sk():
    pytest.importorskip("pynostr")
    pytest.importorskip("bech32")
    from pynostr.key import PrivateKey

    return PrivateKey()


def _write_pub(root: Path, role: str, sk) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{role}.pub.json").write_text(
        json.dumps(
            {
                "name": role,
                "npub": sk.public_key.bech32(),
                "pubkey_hex": sk.public_key.hex(),
            }
        ),
        encoding="utf-8",
    )


def _signed(sk, role: str, body: dict, *, kind: int | None = None):
    _examples_path()
    from nostr_common import sign_json_event

    from agent_bitcoin.nostr.merchant_coord import COORD_TAG, KIND_MERCHANT

    return sign_json_event(
        sk,
        body,
        kind=KIND_MERCHANT if kind is None else kind,
        tags=[
            ["t", COORD_TAG],
            ["role", role],
            ["client", "agent-bitcoin-merchant"],
        ],
    )


def _body(sk, **extra) -> dict:
    payload = {
        "type": "negotiate",
        "v": 1,
        "invoice_id": IID,
        "round": 1,
        "npub": sk.public_key.bech32(),
        "score": 1,
    }
    payload.update(extra)
    return payload


def _wire(event) -> dict:
    from agent_bitcoin.nostr.ws_relay import event_to_dict

    return event_to_dict(event)


def test_accept_rejects_bad_id_sig_kind_invoice_role_and_secrets(
    tmp_path: Path,
) -> None:
    from agent_bitcoin.nostr.merchant_coord import KIND_MERCHANT, accept

    alice = _sk()
    bob = _sk()
    _write_pub(tmp_path, "alice", alice)
    good = _signed(alice, "alice", _body(alice))
    assert accept(_wire(good), IID, key_dir=tmp_path, round_n=1)

    bad_id = _wire(good)
    bad_id["id"] = "ab" * 32
    assert not accept(bad_id, IID, key_dir=tmp_path, round_n=1)

    bad_sig = _wire(good)
    bad_sig["sig"] = "cd" * 64
    assert not accept(bad_sig, IID, key_dir=tmp_path, round_n=1)

    kind1 = _signed(alice, "alice", _body(alice), kind=1)
    assert int(kind1.kind) == 1
    assert not accept(_wire(kind1), IID, key_dir=tmp_path, round_n=1)

    other = _signed(alice, "alice", _body(alice, invoice_id="0123456789abcdef"))
    assert not accept(_wire(other), IID, key_dir=tmp_path, round_n=1)

    leaked = _signed(alice, "alice", _body(alice, bolt11="lnbc1secret"))
    assert not accept(_wire(leaked), IID, key_dir=tmp_path, round_n=1)

    _write_pub(tmp_path, "bob", bob)
    impersonate = _signed(bob, "alice", _body(bob))
    assert not accept(_wire(impersonate), IID, key_dir=tmp_path, round_n=1)
    assert KIND_MERCHANT == 8139


def test_mock_publish_and_wait(tmp_path: Path) -> None:
    from agent_bitcoin.nostr.merchant_coord import publish, wait_event

    alice = _sk()
    _write_pub(tmp_path, "alice", alice)
    publish(_signed(alice, "alice", _body(alice)), offline=True)
    got = wait_event(
        offline=True,
        invoice_id=IID,
        msg_type="negotiate",
        role="alice",
        timeout=2,
        since=0,
        key_dir=tmp_path,
        round_n=1,
    )
    assert got.verify()
    assert json.loads(got.content)["type"] == "negotiate"


def test_pytest_refuses_live_relay() -> None:
    from agent_bitcoin.nostr.ws_relay import publish_event

    with pytest.raises(SystemExit, match="pytest"):
        publish_event(
            {"content": "{}", "kind": 1, "tags": [], "id": "aa", "sig": "bb"},
            ["wss://relay.damus.io"],
        )


def test_stale_result_on_mock_refuses_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agent_bitcoin.nostr.merchant_coord import publish

    alice = _sk()
    _write_pub(tmp_path, "alice", alice)
    publish(
        _signed(
            alice,
            "alice",
            {
                "type": "result",
                "v": 1,
                "invoice_id": IID,
                "round": 1,
                "payer_npub": alice.public_key.bech32(),
                "paid": True,
                "amount_sats": 100,
                "http_status": 200,
                "summary": {"fast": 3, "medium": 2, "slow": 1},
            },
        ),
        offline=True,
    )
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--role",
            "alice",
            "--offline-bus",
            "--no-llm",
            "--dir",
            str(tmp_path),
            "--timeout",
            "5",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert "Stale result" in out
    assert "create_client" not in out
    assert not (tmp_path / "bus").exists()


def test_two_terminals_mock_relay_no_shared_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    env = {
        **os.environ,
        "NOSTR_PASSPHRASE": "test-offline-passphrase-not-a-secret",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    base = [
        sys.executable,
        str(EXAMPLE),
        "--offline-bus",
        "--no-llm",
        "--dir",
        str(tmp_path),
        "--timeout",
        "25",
    ]
    alice = subprocess.Popen(
        [*base, "--role", "alice"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    bob = subprocess.Popen(
        [*base, "--role", "bob"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        out_b, err_b = bob.communicate(timeout=45)
        out_a, err_a = alice.communicate(timeout=45)
    except subprocess.TimeoutExpired:
        alice.kill()
        bob.kill()
        raise
    out = (out_a or "") + (err_a or "") + (out_b or "") + (err_b or "")
    assert alice.returncode == 0, out
    assert bob.returncode == 0, out
    assert "paid=True" in out
    assert "i_pay=True" in out
    assert "i_pay=False" in out
    assert "waiting for signed result" in out
    assert "nsec1" not in out.lower()
    assert "create_client" not in out
    assert not (tmp_path / "bus").exists()
    assert (tmp_path / "alice.pub.json").is_file()
    assert (tmp_path / "bob.pub.json").is_file()
