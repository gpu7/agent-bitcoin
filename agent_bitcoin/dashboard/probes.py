"""Read-only probes for the Mac infrastructure map.

Allowed LND commands are getinfo and listchannels. Nothing here unlocks a
wallet, pays an invoice, or opens a channel.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_SECRET_RE = re.compile(
    r"(nsec1[a-z0-9]+|macaroon\S*|password\s*[:=]\s*\S+|[0-9a-f]{32,})",
    re.IGNORECASE,
)
ALLOWED_LNCLI = frozenset({"getinfo", "listchannels"})
_PAYER = {
    "regtest": ("agent-bitcoin-lnd", "l402-client-lnd"),
    "signet": ("agent-bitcoin-lnd-signet",),
    "mainnet": ("agent-bitcoin-lnd-mainnet", "l402-client-lnd"),
}
_INVOICE = {
    "regtest": ("agent-payment-decision-lnd",),
    "signet": ("agent-payment-decision-lnd-signet",),
    "mainnet": ("agent-payment-decision-lnd-mainnet",),
}
_BITCOIND = {
    "regtest": ("bitcoind",),
    "signet": ("agent-bitcoin-bitcoind-signet",),
    "mainnet": (
        "agent-bitcoin-bitcoind-mainnet",
        "agent-payment-decision-bitcoind-mainnet",
    ),
}


class CommandRejected(RuntimeError):
    """A probe asked for a command this dashboard does not run."""


def scrub(text: str, limit: int = 140) -> str:
    """Drop secrets and collapse a probe error to one short line."""
    cleaned = _SECRET_RE.sub("[redacted]", text or "")
    cleaned = " ".join(cleaned.split())
    return cleaned[:limit]


def network_name(explicit: str | None = None) -> str:
    """Dashboard default is mainnet. This does not read LND_NETWORK."""
    raw = (explicit or "mainnet").strip().lower()
    if raw not in _PAYER:
        raise SystemExit("dashboard --network must be mainnet, regtest, or signet")
    return raw


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    state: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "state": self.state,
            "detail": scrub(self.detail),
        }


class ProbeIO(Protocol):
    def containers(self) -> set[str]: ...

    def lncli(self, container: str, network: str, command: str) -> tuple[int, str]: ...

    def http_status(self, url: str) -> tuple[int | None, str]: ...

    def tcp_open(self, host: str, port: int) -> tuple[bool, str]: ...

    def git_describe(self) -> str: ...

    def relay_hosts(self) -> list[str]: ...


def _first_running(names: set[str], candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        if name in names:
            return name
    return None


def _classify_getinfo(code: int, raw: str) -> tuple[str, str]:
    low = (raw or "").lower()
    if "wallet locked" in low or "wallet is encrypted" in low:
        return "locked", "wallet locked"
    if code != 0:
        return "down", scrub(raw) or "getinfo failed"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "unknown", scrub(raw) or "getinfo was not json"
    if data.get("synced_to_chain") is True:
        return "up", "synced to chain"
    if data.get("synced_to_chain") is False:
        return "up", "unlocked, not synced to chain"
    return "unknown", "getinfo had no chain status"


def _active_channels(raw: str) -> int | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    channels = data.get("channels")
    if not isinstance(channels, list):
        return None
    return sum(
        1 for ch in channels if isinstance(ch, dict) and ch.get("active") is True
    )


def collect_status(io: ProbeIO, *, network: str | None = None) -> dict[str, object]:
    """Build the map. A failed probe stays failed; nothing is marked up by default."""
    net = network or network_name()
    names = io.containers()
    payer = _first_running(names, _PAYER.get(net, _PAYER["regtest"]))
    invoice = _first_running(names, _INVOICE.get(net, _INVOICE["regtest"]))
    bitcoind = _first_running(names, _BITCOIND.get(net, _BITCOIND["regtest"]))

    payer_state, payer_detail = _lnd_node(
        io, payer, net, "payer container is not running"
    )
    invoice_state, invoice_detail = _lnd_node(
        io, invoice, net, "invoice LND is not on this Mac"
    )
    if invoice is None and not getattr(io, "note", ""):
        invoice_state = "unknown"

    bitcoin = _bitcoin(io, payer, payer_state, bitcoind, net)
    channel = _channel(io, payer, payer_state, net)
    aperture = _aperture(io)
    origin = _origin(names)
    note = scrub(getattr(io, "note", "") or "")
    if note and "agent-l402-origin" not in names:
        origin = ("down", note)
    nostr = _nostr(io)

    nodes = [
        Node("bitcoin", "Bitcoin network", *bitcoin),
        Node("channel", "Lightning channel", *channel),
        Node("payer", "Payer agent", payer_state, payer_detail),
        Node("invoice", "Invoice agent", invoice_state, invoice_detail),
        Node("nostr", "Nostr", *nostr),
        Node("aperture", "Aperture", *aperture),
        Node("origin", "Merchant origin", *origin),
    ]
    links = [
        ["bitcoin", "channel"],
        ["channel", "payer"],
        ["channel", "invoice"],
        ["payer", "nostr"],
        ["invoice", "nostr"],
        ["invoice", "aperture"],
        ["aperture", "origin"],
    ]
    try:
        revision = scrub(io.git_describe(), limit=80) or "unknown"
    except Exception:  # noqa: BLE001 — revision stays unknown; no exception text
        revision = "unknown"
    return {
        "revision": revision,
        "network": net,
        "bind": "127.0.0.1",
        "nodes": [node.as_dict() for node in nodes],
        "links": links,
    }


def _lnd_node(
    io: ProbeIO, container: str | None, network: str, absent: str
) -> tuple[str, str]:
    if container is None:
        note = scrub(getattr(io, "note", "") or "")
        return "down", note or absent
    code, raw = io.lncli(container, network, "getinfo")
    return _classify_getinfo(code, raw)


def _bitcoin(
    io: ProbeIO,
    payer: str | None,
    payer_state: str,
    bitcoind: str | None,
    network: str,
) -> tuple[str, str]:
    if payer and payer_state == "up":
        code, raw = io.lncli(payer, network, "getinfo")
        state, detail = _classify_getinfo(code, raw)
        if state == "up" and detail == "synced to chain":
            return "up", "payer sees the chain"
        if state == "up":
            return "unknown", detail
        return state, detail
    if payer_state == "locked":
        return "unknown", "payer wallet locked"
    if bitcoind:
        return "up", f"{bitcoind} container running"
    if payer_state == "down":
        return "unknown", "no bitcoind container and payer LND is down"
    return "unknown", "chain sync was not read"


def _channel(
    io: ProbeIO, payer: str | None, payer_state: str, network: str
) -> tuple[str, str]:
    if payer is None:
        return "unknown", "payer container is not running"
    if payer_state == "locked":
        return "locked", "payer wallet locked"
    if payer_state != "up":
        return "unknown", "payer getinfo did not succeed"
    code, raw = io.lncli(payer, network, "listchannels")
    if code != 0:
        return "unknown", scrub(raw) or "listchannels failed"
    count = _active_channels(raw)
    if count is None:
        return "unknown", "listchannels was not json"
    if count == 0:
        return "down", "no active channel"
    label = "1 active channel" if count == 1 else f"{count} active channels"
    return "up", label


def _aperture(io: ProbeIO) -> tuple[str, str]:
    base = (os.environ.get("DASHBOARD_APERTURE_URL") or "http://127.0.0.1:8081").rstrip(
        "/"
    )
    health_code, health_err = io.http_status(base + "/health")
    if health_code is None:
        return "down", scrub(health_err) or "health probe failed"
    if health_code != 200:
        return "down", f"health HTTP {health_code}"
    hello_code, hello_err = io.http_status(base + "/paid/hello")
    if hello_code is None:
        return "down", scrub(hello_err) or "hello probe failed"
    if hello_code == 402:
        return "up", "health 200, unpaid hello 402"
    return "unknown", f"hello HTTP {hello_code}, expected 402"


def _origin(names: set[str]) -> tuple[str, str]:
    if "agent-l402-origin" in names:
        return "up", "container running on this Mac"
    return "unknown", "origin container is not on this Mac"


def _nostr(io: ProbeIO) -> tuple[str, str]:
    hosts = io.relay_hosts()
    if not hosts:
        return "unknown", "NOSTR_RELAYS is empty"
    errors: list[str] = []
    for host in hosts:
        ok, detail = io.tcp_open(host, 443)
        if ok:
            return "up", f"{host}:443 accepted a connection"
        errors.append(scrub(detail) or f"{host} failed")
    return "down", errors[0]


class RealProbeIO:
    """Subprocess and HTTP probes. Refuses pay, unlock, and live calls under pytest."""

    note: str = ""

    def containers(self) -> set[str]:
        try:
            done = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            self.note = "docker probe failed"
            return set()
        self.note = ""
        if done.returncode != 0:
            self.note = scrub(done.stderr) or "docker ps failed"
            return set()
        return {line.strip() for line in done.stdout.splitlines() if line.strip()}

    def lncli(self, container: str, network: str, command: str) -> tuple[int, str]:
        if command not in ALLOWED_LNCLI:
            raise CommandRejected(command)
        try:
            done = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "lncli",
                    "--lnddir=/home/lnd/.lnd",
                    "--network",
                    network,
                    command,
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return 1, "lncli probe failed"
        return done.returncode, (done.stdout or "") + (done.stderr or "")

    def http_status(self, url: str) -> tuple[int | None, str]:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return None, "skipped during pytest"
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=3) as response:  # noqa: S310 — operator URL
                return int(response.status), ""
        except HTTPError as exc:
            return int(exc.code), ""
        except (URLError, TimeoutError, OSError):
            return None, "connection failed"

    def tcp_open(self, host: str, port: int) -> tuple[bool, str]:
        if os.environ.get("PYTEST_CURRENT_TEST"):
            return False, "skipped during pytest"
        try:
            with socket.create_connection((host, port), timeout=2):
                return True, ""
        except OSError:
            return False, "connection failed"

    def git_describe(self) -> str:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        try:
            done = subprocess.run(
                ["git", "describe", "--tags", "--always", "--dirty"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                cwd=root,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unknown"
        if done.returncode != 0:
            return scrub(done.stderr) or "unknown"
        return (done.stdout or "").strip() or "unknown"

    def relay_hosts(self) -> list[str]:
        raw = os.environ.get("NOSTR_RELAYS") or "wss://relay.damus.io,wss://nos.lol"
        hosts: list[str] = []
        for part in raw.split(","):
            item = part.strip()
            if not item:
                continue
            item = item.split("://", 1)[-1]
            host = item.split("/", 1)[0].split(":", 1)[0]
            if host:
                hosts.append(host)
        return hosts
