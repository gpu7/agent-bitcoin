"""Offline swarm L402 negotiate: scores, bus signatures, mock pay. No live LND."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_bitcoin.nostr.negotiate import (
    choose_payer,
    fee_band_summary,
    invoice_id_for_url,
    negotiate_score,
    negotiate_score_hex,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "swarm_l402_negotiate.py"


def test_invoice_id_stable() -> None:
    url = "http://127.0.0.1:8081/paid/finance/mempool-feerate"
    iid = invoice_id_for_url(url)
    assert iid == invoice_id_for_url(url)
    assert len(iid) == 16
    assert iid == hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def test_score_matches_spec() -> None:
    pk = "ab" * 32
    iid = "deadbeefdeadbeef"
    score, hx = negotiate_score_hex(pk, iid, 1)
    raw = hashlib.sha256(f"{pk}{iid}1".encode("utf-8")).hexdigest()
    assert hx == raw[:8]
    assert score == int(raw[:8], 16)
    assert negotiate_score(pk.upper(), iid, 1) == score


def test_higher_score_pays() -> None:
    winner, reason = choose_payer("npub1aaa", 10, "npub1bbb", 3)
    assert winner == "npub1aaa"
    assert reason == "lower_score"
    winner, reason = choose_payer("npub1aaa", 1, "npub1bbb", 9)
    assert winner == "npub1bbb"
    assert reason == "lower_score"


def test_tie_greater_npub_pays() -> None:
    winner, reason = choose_payer("npub1aaa", 7, "npub1zzz", 7)
    assert winner == "npub1zzz"
    assert reason == "tie_npub"


def test_fee_band_summary_strips_other_keys() -> None:
    summary = fee_band_summary(
        {
            "ok": True,
            "fast": 4,
            "medium": 2,
            "slow": 1,
            "source": "do-not-log",
            "as_of": "2026-09-10T00:00:00Z",
        }
    )
    assert summary == {"fast": 4, "medium": 2, "slow": 1}
    assert fee_band_summary("not-json") == {}
    assert fee_band_summary({"fast": "x"}) == {}


def test_signed_bus_roundtrip(tmp_path: Path) -> None:
    pytest.importorskip("pynostr")
    sys.path.insert(0, str(ROOT / "examples"))
    from pynostr.event import EventKind

    from nostr_common import (  # noqa: E402
        parse_payload,
        read_bus_event,
        sign_json_event,
        write_bus_event,
    )
    from pynostr.key import PrivateKey

    alice = PrivateKey()
    bob = PrivateKey()
    iid = invoice_id_for_url("http://127.0.0.1:8081/paid/finance/mempool-feerate")
    a_score, a_hex = negotiate_score_hex(alice.public_key.hex(), iid, 1)
    b_score, b_hex = negotiate_score_hex(bob.public_key.hex(), iid, 1)
    bus = tmp_path / "bus"
    ev_a = sign_json_event(
        alice,
        {
            "type": "negotiate",
            "v": 1,
            "invoice_id": iid,
            "round": 1,
            "npub": alice.public_key.bech32(),
            "score": a_score,
            "score_hex": a_hex,
        },
        kind=EventKind.TEXT_NOTE,
        tags=[["t", "agent-bitcoin-swarm-l402-v1"]],
    )
    write_bus_event(bus, f"{iid}_alice_negotiate.json", ev_a)
    ev_b = sign_json_event(
        bob,
        {
            "type": "negotiate",
            "v": 1,
            "invoice_id": iid,
            "round": 1,
            "npub": bob.public_key.bech32(),
            "score": b_score,
            "score_hex": b_hex,
        },
        kind=EventKind.TEXT_NOTE,
        tags=[["t", "agent-bitcoin-swarm-l402-v1"]],
    )
    write_bus_event(bus, f"{iid}_bob_negotiate.json", ev_b)

    got_a = read_bus_event(bus / f"{iid}_alice_negotiate.json")
    got_b = read_bus_event(bus / f"{iid}_bob_negotiate.json")
    assert got_a.verify()
    assert got_b.verify()
    pa = parse_payload(got_a)
    pb = parse_payload(got_b)
    # Recompute from signed pubkey — do not trust payload.score alone
    sa = negotiate_score(got_a.pubkey, iid, 1)
    sb = negotiate_score(got_b.pubkey, iid, 1)
    assert sa == pa["score"]
    assert sb == pb["score"]
    winner, _reason = choose_payer(pa["npub"], sa, pb["npub"], sb)
    assert winner in {pa["npub"], pb["npub"]}


def test_offline_both_cli_no_live_pay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("pynostr")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_BITCOIN_ALLOW_MAINNET", raising=False)
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
            "both",
            "--offline-bus",
            "--no-llm",
            "--force-new-keys",
            "--dir",
            str(tmp_path),
            "--timeout",
            "15",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "paid=True" in out
    assert "npub1" in out
    assert "nsec1" not in out.lower()
    # Mock pay only — no LND client construction in the offline path
    assert "create_client" not in out
    bus_files = list((tmp_path / "bus").glob("*.json"))
    names = {p.name for p in bus_files}
    assert any(n.endswith("_alice_negotiate.json") for n in names)
    assert any(n.endswith("_bob_negotiate.json") for n in names)
    assert any(n.endswith("_result.json") for n in names)
    result_path = next(p for p in bus_files if p.name.endswith("_result.json"))
    body = json.loads(result_path.read_text(encoding="utf-8"))
    payload = json.loads(body["content"])
    assert payload["type"] == "result"
    assert payload["paid"] is True
    assert "preimage" not in payload
    assert "macaroon" not in json.dumps(payload)
