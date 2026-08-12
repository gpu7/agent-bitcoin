"""Offline tests for public-relay NWC listen/connect (no live websockets)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

pytest.importorskip("pynostr")

from agent_bitcoin.nwc.errors import NWCError  # noqa: E402
from agent_bitcoin.nwc.policy import KIND_REQUEST, KIND_RESPONSE  # noqa: E402
from agent_bitcoin.nostr.relay import (  # noqa: E402
    CONNECT_TIMEOUT,
    WebsocketNWCRelay,
    probe_relay,
    register_relays,
    run_nwc_listen_session,
    select_live_relays,
)


class _FakePool:
    def __init__(self, events: list | None = None) -> None:
        self._events = list(events or [])

    def has_events(self) -> bool:
        return bool(self._events)

    def get_event(self):
        return SimpleNamespace(event=self._events.pop(0))


class _FakeMgr:
    def __init__(self) -> None:
        self.relays: dict[str, dict] = {}
        self.message_pool = _FakePool()
        self.subscriptions: list[tuple[str, object]] = []
        self.closed = False
        self.sync_calls = 0

    def add_relay(self, url: str, timeout=2.0, close_on_eose=True, **kwargs):
        if "fail" in url:
            raise RuntimeError("refused")
        self.relays[url] = {
            "timeout": timeout,
            "close_on_eose": close_on_eose,
        }

    def add_subscription_on_all_relays(self, sub_id: str, filters) -> None:
        self.subscriptions.append((sub_id, filters))

    def run_sync(self) -> None:
        self.sync_calls += 1

    def close_all_relay_connections(self) -> None:
        self.closed = True

    def publish_event(self, event) -> None:
        self.published = event


def test_register_relays_skips_dead() -> None:
    mgr = _FakeMgr()
    logs: list[str] = []
    added = register_relays(
        mgr,
        ["wss://ok.example", "wss://fail.example"],
        close_on_eose=False,
        timeout=2.0,
        log=logs.append,
    )
    assert added == ["wss://ok.example"]
    assert mgr.relays["wss://ok.example"]["close_on_eose"] is False
    assert any("skip wss://fail.example" in line for line in logs)


def test_probe_relay_hard_deadline_does_not_block() -> None:
    def _hang(url: str, timeout: float) -> None:
        time.sleep(10)

    start = time.monotonic()
    ok = probe_relay("wss://hung.example", timeout=0.2, _connect=_hang)
    elapsed = time.monotonic() - start
    assert ok is False
    assert elapsed < 2.5


def test_probe_relay_ok_and_error() -> None:
    assert probe_relay("wss://ok", timeout=0.5, _connect=lambda u, t: None) is True

    def _boom(url: str, timeout: float) -> None:
        raise OSError("down")

    assert probe_relay("wss://bad", timeout=0.5, _connect=_boom) is False


def test_select_live_relays_logs_per_url() -> None:
    logs: list[str] = []

    def _probe(url: str, timeout: float = 2.0) -> bool:
        return url.endswith("live")

    live = select_live_relays(
        ["wss://a.live", "wss://b.dead"],
        log=logs.append,
        probe=_probe,
    )
    assert live == ["wss://a.live"]
    assert any("connecting wss://a.live" in line for line in logs)
    assert any(line == "ok wss://a.live" for line in logs)
    assert any("skip wss://b.dead" in line for line in logs)


def test_listen_session_logs_subscribed_and_keeps_socket() -> None:
    logs: list[str] = []
    requests: list[dict] = []
    mgr = _FakeMgr()
    ev = SimpleNamespace(
        id="req1",
        pubkey="aa" * 32,
        created_at=1,
        kind=KIND_REQUEST,
        tags=[["p", "wallet"]],
        content="cipher",
        sig="sig",
    )
    mgr.message_pool = _FakePool([ev])
    polls = {"n": 0}

    def _stop() -> bool:
        polls["n"] += 1
        return polls["n"] > 1

    run_nwc_listen_session(
        ["wss://a.live", "wss://b.dead"],
        "walletpubkey",
        requests.append,
        log=logs.append,
        stop=_stop,
        poll_sleep=0,
        probe=lambda url, timeout=2.0: url.endswith("live"),
        manager_factory=lambda: mgr,
    )
    assert any("subscribed, polling" in line for line in logs)
    assert mgr.relays["wss://a.live"]["close_on_eose"] is False
    assert "wss://b.dead" not in mgr.relays
    assert len(requests) == 1
    assert requests[0]["id"] == "req1"
    assert len(mgr.subscriptions) >= 1


def test_listen_resubscribes_each_poll_and_publishes_on_same_manager() -> None:
    mgr = _FakeMgr()
    polls = {"n": 0}

    def _stop() -> bool:
        polls["n"] += 1
        return polls["n"] > 2

    reply = {
        "id": "resp1",
        "pubkey": "bb" * 32,
        "created_at": 2,
        "kind": KIND_RESPONSE,
        "tags": [["e", "req1"], ["p", "client"]],
        "content": "cipher-out",
        "sig": "sig",
    }

    def _on_request(d: dict) -> dict:
        return reply

    ev = SimpleNamespace(
        id="req1",
        pubkey="aa" * 32,
        created_at=1,
        kind=KIND_REQUEST,
        tags=[["p", "wallet"]],
        content="cipher",
        sig="sig",
    )
    mgr.message_pool = _FakePool([ev])

    run_nwc_listen_session(
        ["wss://a.live"],
        "walletpubkey",
        _on_request,
        stop=_stop,
        poll_sleep=0,
        probe=lambda url, timeout=2.0: True,
        manager_factory=lambda: mgr,
    )
    assert len(mgr.subscriptions) >= 2
    assert getattr(mgr, "published", None) is not None


def test_listen_session_raises_when_all_relays_dead() -> None:
    with pytest.raises(NWCError, match="no public relays"):
        run_nwc_listen_session(
            ["wss://dead"],
            "wallet",
            lambda d: None,
            probe=lambda url, timeout=2.0: False,
        )


def test_wait_for_response_does_not_close_on_eose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    added: list[dict] = []
    managers: list[_FakeMgr] = []

    class _Mgr(_FakeMgr):
        def __init__(self, timeout=None) -> None:  # noqa: ANN001
            assert timeout is None, "must not pass RPC wait as RelayManager.timeout"
            super().__init__()
            managers.append(self)

        def add_relay(self, url: str, timeout=2.0, close_on_eose=True, **kwargs):
            added.append(
                {
                    "url": url,
                    "timeout": timeout,
                    "close_on_eose": close_on_eose,
                    "manager_timeout": None,
                }
            )
            return super().add_relay(
                url, timeout=timeout, close_on_eose=close_on_eose, **kwargs
            )

    monkeypatch.setattr("agent_bitcoin.nostr.relay.RelayManager", _Mgr)
    ws = WebsocketNWCRelay(["wss://ok.example"], timeout=20.0)
    with pytest.raises(NWCError, match="timeout waiting"):
        ws.wait_for_response(
            request_event_id="evt",
            client_pubkey="client",
            timeout=0.05,
        )
    assert added
    assert added[0]["close_on_eose"] is False
    assert added[0]["timeout"] == CONNECT_TIMEOUT
    assert managers[0].closed is True


def test_publish_is_oneshot_close_on_eose(monkeypatch: pytest.MonkeyPatch) -> None:
    added: list[dict] = []

    class _Mgr(_FakeMgr):
        def add_relay(self, url: str, timeout=2.0, close_on_eose=True, **kwargs):
            added.append({"close_on_eose": close_on_eose, "timeout": timeout})
            return super().add_relay(
                url, timeout=timeout, close_on_eose=close_on_eose, **kwargs
            )

    monkeypatch.setattr("agent_bitcoin.nostr.relay.RelayManager", _Mgr)
    ws = WebsocketNWCRelay(["wss://ok.example"], timeout=20.0)
    ws.publish(
        {
            "kind": KIND_RESPONSE,
            "content": "x",
            "tags": [],
            "pubkey": "aa" * 32,
            "id": "id1",
            "sig": "sig",
            "created_at": 1,
        }
    )
    assert added[0]["close_on_eose"] is True
    assert added[0]["timeout"] == CONNECT_TIMEOUT
