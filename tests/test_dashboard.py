"""The infrastructure map is read-only and does not return secrets."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from agent_bitcoin.dashboard.app import (
    create_app,
    resolve_host,
    resolve_network,
    resolve_port,
)
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


def _client(io: FakeIO) -> TestClient:
    return TestClient(create_app(io))


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
    assert ">Refresh<" in html
    assert ">Pay<" not in html
    assert ">Unlock<" not in html
