"""The infrastructure map is read-only and does not return secrets."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_bitcoin.dashboard.app import (
    create_app,
    resolve_host,
    resolve_network,
    resolve_port,
)
from agent_bitcoin.dashboard.npub import default_npub_dir, picture_labels, short_npub
from agent_bitcoin.dashboard.probes import (
    ALLOWED_LNCLI,
    CommandRejected,
    RealProbeIO,
    collect_status,
)


class FakeIO:
    def __init__(self) -> None:
        self.names = {"agent-bitcoin-lnd", "agent-l402-origin"}
        self.calls: list[str] = []
        self.note = ""
        self.getinfo = '{"synced_to_chain": true}'
        self.getinfo_code = 0
        self.channels = '{"channels": [{"active": true}]}'
        self.http = {
            "http://127.0.0.1:8081/health": (200, ""),
            "http://127.0.0.1:8081/paid/hello": (402, ""),
        }

    def containers(self) -> set[str]:
        return set(self.names)

    def lncli(self, container: str, network: str, command: str) -> tuple[int, str]:
        self.calls.append(command)
        if command not in ALLOWED_LNCLI:
            raise CommandRejected(command)
        if command == "listchannels":
            return 0, self.channels
        return self.getinfo_code, self.getinfo

    def http_status(self, url: str) -> tuple[int | None, str]:
        self.calls.append("GET " + url)
        return self.http.get(url, (None, "connection refused"))

    def tcp_open(self, host: str, port: int) -> tuple[bool, str]:
        self.calls.append(f"tcp {host}:{port}")
        return True, ""

    def git_describe(self) -> str:
        return "v.test"

    def relay_hosts(self) -> list[str]:
        return ["relay.example"]


_NO_NPUB_DIR = Path("/nonexistent/agent-bitcoin-dashboard-npubs")
_ALICE = "npub1u9z2exv9udv2hkhnq5fl8pvlsqvuphmuuxejj2u6g0lf06r8tgsqxl68s8"
_BOB = "npub1jy3ch65u5wvhx4x5s7239k63qtp65h4084fcaq8djgra0dh0erfslusp9f"


def _client(io: FakeIO, npub_dir: Path | None = None) -> TestClient:
    return TestClient(create_app(io, npub_dir=npub_dir or _NO_NPUB_DIR))


def test_status_is_read_only_and_has_no_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LND_NETWORK", "regtest")
    monkeypatch.delenv("AGENT_BITCOIN_ALLOW_AUTOPAY", raising=False)
    monkeypatch.delenv("DASHBOARD_APERTURE_URL", raising=False)
    io = FakeIO()
    io.names = {
        "agent-bitcoin-lnd-mainnet",
        "agent-payment-decision-lnd-mainnet",
        "agent-payment-decision-bitcoind-mainnet",
        "agent-l402-origin",
    }
    response = _client(io).get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["bind"] == "127.0.0.1"
    assert body["network"] == "mainnet"
    assert os.environ.get("AGENT_BITCOIN_ALLOW_AUTOPAY") is None
    states = {node["id"]: node["state"] for node in body["nodes"]}
    assert states == {
        "bitcoin": "up",
        "channel": "up",
        "payer": "up",
        "invoice": "up",
        "nostr": "up",
        "aperture": "up",
        "origin": "up",
    }
    assert set(io.calls) <= {
        "getinfo",
        "listchannels",
        *{c for c in io.calls if c.startswith(("GET ", "tcp "))},
    }
    assert "unlock" not in io.calls
    assert "sendpayment" not in io.calls
    assert "payinvoice" not in io.calls
    assert "openchannel" not in io.calls
    text = response.text.lower()
    assert "nsec1" not in text
    assert "macaroon" not in text
    assert "password" not in text


def test_status_hides_probe_exception_text() -> None:
    class Boom(FakeIO):
        def containers(self) -> set[str]:
            raise RuntimeError("nsec1shouldnotappear macaroon=secret password=hunter2")

    normal = _client(FakeIO()).get("/api/status")
    assert normal.status_code == 200

    response = _client(Boom()).get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["bind"] == "127.0.0.1"
    assert [node["state"] for node in body["nodes"]] == ["unknown"] * 7
    assert {node["detail"] for node in body["nodes"]} == {"probe failed"}
    text = response.text.lower()
    assert "nsec1shouldnotappear" not in text
    assert "macaroon" not in text
    assert "password" not in text
    assert "hunter2" not in text
    assert "traceback" not in text


def test_failed_probe_is_not_marked_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LND_NETWORK", "regtest")
    monkeypatch.delenv("DASHBOARD_APERTURE_URL", raising=False)
    io = FakeIO()
    io.names = set()
    io.http = {}
    io.getinfo_code = 1
    io.getinfo = "nsec1secretdemo macaroon=aabb password=nope"
    payload = collect_status(io, network="regtest")
    by_id = {node["id"]: node for node in payload["nodes"]}
    assert by_id["payer"]["state"] == "down"
    assert by_id["payer"]["state"] != "up"
    assert by_id["aperture"]["state"] == "down"
    assert by_id["bitcoin"]["state"] != "up"
    blob = str(payload).lower()
    assert "nsec1" not in blob
    assert "macaroon" not in blob
    assert "password=" not in blob


def test_wallet_locked_is_locked_not_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LND_NETWORK", "regtest")
    io = FakeIO()
    io.getinfo_code = 1
    io.getinfo = "rpc error: wallet locked"
    payload = collect_status(io, network="regtest")
    by_id = {node["id"]: node for node in payload["nodes"]}
    assert by_id["payer"]["state"] == "locked"
    assert by_id["channel"]["state"] == "locked"
    assert "listchannels" not in io.calls
    assert "unlock" not in io.calls


def test_lncli_guard_rejects_unlock(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr("agent_bitcoin.dashboard.probes.subprocess.run", boom)
    with pytest.raises(CommandRejected):
        RealProbeIO().lncli("agent-bitcoin-lnd", "regtest", "unlock")


def test_default_network_is_mainnet_and_lab_override_is_explicit() -> None:
    assert resolve_network([]) == "mainnet"
    assert resolve_network(["--network", "regtest"]) == "regtest"
    assert resolve_network(["--network", "signet"]) == "signet"
    from agent_bitcoin.lightning import _DEFAULT_NETWORK

    assert _DEFAULT_NETWORK == "regtest"


def test_bind_is_loopback_only() -> None:
    assert resolve_host("127.0.0.1") == "127.0.0.1"
    with pytest.raises(SystemExit):
        resolve_host("0.0.0.0")
    with pytest.raises(SystemExit):
        resolve_port("10009")
    assert resolve_port("8765") == 8765


def test_page_lists_the_map_and_has_no_pay_button() -> None:
    html = _client(FakeIO()).get("/").text
    for label in (
        "Bitcoin network",
        "Lightning channel",
        "Payer agent",
        "Invoice agent",
        "Nostr",
        "Aperture",
        "Merchant origin",
    ):
        assert label in html
    after_chain = html.split('id="group-chain"', 1)[1]
    chain, after_agents = after_chain.split('id="group-agents"', 1)
    agents, merchant = after_agents.split('id="group-merchant"', 1)
    assert ">Chain<" in chain
    assert 'id="bitcoin"' in chain and 'id="channel"' in chain
    assert ">Agents<" in agents
    assert (
        'id="payer"' in agents and 'id="invoice"' in agents and 'id="nostr"' in agents
    )
    assert 'id="bitcoin"' not in agents
    assert ">Merchant<" in merchant
    assert 'id="aperture"' in merchant and 'id="origin"' in merchant
    assert 'id="payer"' not in merchant
    for pair in (
        '["bitcoin", "channel"]',
        '["channel", "payer"]',
        '["channel", "invoice"]',
        '["payer", "nostr"]',
        '["invoice", "nostr"]',
        '["invoice", "aperture"]',
        '["aperture", "origin"]',
    ):
        assert pair in html
    story = html.split('id="agent-animation"', 1)[1].split('id="map"', 1)[0]
    assert html.index('id="agent-animation"') < html.index('id="group-chain"')
    assert "Agent 1" in story and "Agent 2" in story
    assert story.count("agent npub") == 2
    assert "100 sats" in story
    assert "offset-path" in html
    assert "@keyframes glide" in html
    assert "not a live channel" in story
    assert story.index("not a live channel.") < story.index('class="story-rule"')
    assert "<button" not in story
    assert 'classList.add("pressed")' in html
    assert 'fetch("/api/status"' in html
    assert "nsec" not in story.lower()
    assert "macaroon" not in story.lower()
    assert ">Refresh<" in html
    assert ">Pay<" not in html
    assert ">Unlock<" not in html
    assert "127.0.0.1" in html
    assert "nsec" not in html.lower()


def test_short_npub_keeps_last_four_and_drops_nsec() -> None:
    assert short_npub(_ALICE) == "npub1…68s8"
    assert short_npub(_BOB) == "npub1…sp9f"
    assert short_npub("nsec1shouldnotappear") == "agent npub"
    assert short_npub("") == "agent npub"
    assert "nsec" not in short_npub("nsec1shouldnotappear")


def test_missing_keys_still_render_the_picture(tmp_path: Path) -> None:
    html = _client(FakeIO(), tmp_path).get("/").text
    assert "Agent 1" in html and "Agent 2" in html
    assert "100 sats" in html
    assert html.count("agent npub") == 2
    assert "nsec" not in html.lower()


def test_picture_npubs_ignore_nsec_files_and_bob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DASHBOARD_AGENT1_NPUB", raising=False)
    monkeypatch.delenv("DASHBOARD_AGENT2_NPUB", raising=False)
    (tmp_path / "alice.pub.json").write_text(
        json.dumps(
            {
                "name": "alice",
                "npub": _ALICE,
                "note": "public only; never return nsec",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "alice.enc.json").write_text("nsec1shouldnotappear", encoding="utf-8")
    (tmp_path / "bob.pub.json").write_text(json.dumps({"npub": _BOB}), encoding="utf-8")
    regtest = tmp_path / ".nostr-poc"
    regtest.mkdir()
    (regtest / "alice.pub.json").write_text(
        json.dumps({"npub": _BOB}), encoding="utf-8"
    )

    page = _client(FakeIO(), tmp_path).get("/")
    status = _client(FakeIO(), tmp_path).get("/api/status")
    assert page.status_code == 200
    assert "npub1…68s8" in page.text
    assert "npub1…sp9f" not in page.text
    assert _ALICE not in page.text
    assert "agent npub" in page.text
    assert "nsec" not in page.text.lower()
    assert "nsec" not in status.text.lower()
    assert "nsec1shouldnotappear" not in page.text


def test_npub_env_overrides_and_agent2_is_env_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "alice.pub.json").write_text(
        json.dumps({"npub": _ALICE}), encoding="utf-8"
    )
    (tmp_path / "bob.pub.json").write_text(json.dumps({"npub": _BOB}), encoding="utf-8")
    monkeypatch.setenv("DASHBOARD_AGENT1_NPUB", _BOB)
    monkeypatch.delenv("DASHBOARD_AGENT2_NPUB", raising=False)
    overridden = _client(FakeIO(), tmp_path).get("/").text
    assert "npub1…sp9f" in overridden
    assert "npub1…68s8" not in overridden
    assert _BOB not in overridden

    monkeypatch.setenv("DASHBOARD_AGENT1_NPUB", "nsec1shouldnotappear")
    monkeypatch.setenv("DASHBOARD_AGENT2_NPUB", _BOB)
    rejected = _client(FakeIO(), tmp_path).get("/").text
    assert "npub1…68s8" not in rejected
    assert "npub1…sp9f" in rejected
    assert "agent npub" in rejected
    assert "nsec" not in rejected.lower()


def test_live_mainnet_payer_pub_is_short(monkeypatch: pytest.MonkeyPatch) -> None:
    directory = default_npub_dir()
    if not (directory / "alice.pub.json").is_file():
        pytest.skip("mainnet payer pub is not on this machine")
    monkeypatch.delenv("DASHBOARD_AGENT1_NPUB", raising=False)
    monkeypatch.delenv("DASHBOARD_AGENT2_NPUB", raising=False)
    labels = picture_labels(npub_dir=directory)
    assert labels == ("npub1…68s8", "agent npub")
    html = _client(FakeIO(), directory).get("/").text
    status = _client(FakeIO(), directory).get("/api/status").text
    assert "npub1…68s8" in html
    assert "nsec" not in html.lower()
    assert "nsec" not in status.lower()
