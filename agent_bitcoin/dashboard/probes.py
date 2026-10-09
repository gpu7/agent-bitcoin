"""Read-only probes for the Mac infrastructure map.

Allowed LND commands are getinfo and listchannels. The invoice agent is the
AWS LND, reached with getinfo over the operator SSH path. AWS chain progress
is getblockchaininfo on the AWS bitcoind container. Nothing here unlocks a
wallet, pays an invoice, or opens a channel.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
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
_AWS_BITCOIND = {
    "mainnet": "agent-payment-decision-bitcoind-mainnet",
}
_INVOICE_NAMES = frozenset(name for names in _INVOICE.values() for name in names)
_AWS_BITCOIND_NAMES = frozenset(_AWS_BITCOIND.values())
_DEFAULT_AWS_HOST = "3.90.159.146"
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")


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
    challenge_state: str = ""
    challenge_detail: str = ""

    def as_dict(self) -> dict[str, str]:
        payload = {
            "id": self.id,
            "label": self.label,
            "state": self.state,
            "detail": scrub(self.detail),
        }
        if self.challenge_state:
            payload["challenge_state"] = self.challenge_state
            payload["challenge_detail"] = scrub(self.challenge_detail)
        return payload


class ProbeIO(Protocol):
    def containers(self) -> set[str]: ...

    def lncli(self, container: str, network: str, command: str) -> tuple[int, str]: ...

    def invoice_getinfo(
        self, container: str, network: str
    ) -> tuple[int | None, str]: ...

    def chain_info(self, container: str, network: str) -> tuple[int | None, str]: ...

    def http_status(self, url: str) -> tuple[int | None, str]: ...

    def tcp_open(self, host: str, port: int) -> tuple[bool, str]: ...

    def git_describe(self) -> str: ...

    def relay_hosts(self) -> list[str]: ...


def release_label(root: str) -> str:
    """Nearest git release tag, or a short commit hash when the repo has no tags."""
    tag = _git_stdout(root, ["describe", "--tags", "--abbrev=0"])
    if tag:
        return tag
    return _git_stdout(root, ["rev-parse", "--short", "HEAD"]) or "unknown"


def _git_stdout(root: str, args: list[str]) -> str:
    try:
        done = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=root,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if done.returncode != 0:
        return ""
    lines = (done.stdout or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def _first_running(names: set[str], candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        if name in names:
            return name
    return None


@dataclass(frozen=True)
class _Info:
    state: str
    detail: str
    block_height: int | None = None
    num_peers: int | None = None


def _whole_number(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    return value


def _classify_getinfo(code: int, raw: str) -> _Info:
    low = (raw or "").lower()
    if "wallet locked" in low or "wallet is encrypted" in low:
        return _Info("locked", "wallet locked")
    if code != 0:
        return _Info("down", scrub(raw) or "getinfo failed")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _Info("unknown", scrub(raw) or "getinfo was not json")
    if not isinstance(data, dict):
        return _Info("unknown", "getinfo was not json")
    height = _whole_number(data.get("block_height"))
    peers = _whole_number(data.get("num_peers"))
    if data.get("synced_to_chain") is True:
        return _Info("up", "synced to chain", height, peers)
    if data.get("synced_to_chain") is False:
        return _Info("up", "unlocked, not synced to chain", height, peers)
    return _Info("unknown", "getinfo had no chain status", height, peers)


def _with_height(info: _Info) -> tuple[str, str]:
    if info.block_height is None:
        return info.state, info.detail
    return info.state, f"{info.detail} · height {info.block_height}"


def chain_progress_line(data: dict[str, object]) -> str | None:
    """blocks / headers and percent. Missing fields do not become a guess."""
    blocks = _whole_number(data.get("blocks"))
    headers = _whole_number(data.get("headers"))
    progress = data.get("verificationprogress")
    downloading = data.get("initialblockdownload")
    if blocks is None or headers is None or not isinstance(downloading, bool):
        return None
    if isinstance(progress, bool) or not isinstance(progress, (int, float)):
        return None
    if not 0 <= float(progress) <= 1:
        return None
    percent = int(round(float(progress) * 100))
    return f"{blocks} / {headers}, {percent}%"


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

    payer_info = _lnd_node(io, payer, net, "payer container is not running")
    payer_state, payer_detail = _with_height(payer_info)
    invoice_state, invoice_detail = _invoice(io, net)
    bitcoin = _bitcoin(io, net)
    peers = payer_info.num_peers if payer_state == "up" else None
    channel = _channel(io, payer, payer_state, net, peers)
    aperture, challenge, origin = _merchant(io)
    nostr = _nostr(io)

    nodes = [
        Node("bitcoin", "Bitcoin network", *bitcoin),
        Node("channel", "Lightning channel", *channel),
        Node("payer", "Payer agent", payer_state, payer_detail),
        Node("invoice", "Invoice agent", invoice_state, invoice_detail),
        Node("nostr", "Nostr", *nostr),
        Node("aperture", "Aperture", *aperture, *challenge),
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


def _lnd_node(io: ProbeIO, container: str | None, network: str, absent: str) -> _Info:
    if container is None:
        note = scrub(getattr(io, "note", "") or "")
        return _Info("down", note or absent)
    code, raw = io.lncli(container, network, "getinfo")
    return _classify_getinfo(code, raw)


def _bitcoin(io: ProbeIO, network: str) -> tuple[str, str]:
    """AWS bitcoind progress. A failed read stays unknown and has no invented percent."""
    container = _AWS_BITCOIND.get(network)
    if not container:
        return "unknown", "AWS chain progress was not read"
    try:
        code, raw = io.chain_info(container, network)
    except Exception:  # noqa: BLE001 — chain failure must not change the payer
        return "unknown", "AWS chain progress was not read"
    if code != 0:
        return "unknown", "AWS chain progress was not read"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "unknown", "AWS chain progress was not read"
    if not isinstance(data, dict):
        return "unknown", "AWS chain progress was not read"
    line = chain_progress_line(data)
    if line is None:
        return "unknown", "AWS chain progress was not read"
    if data.get("initialblockdownload") is True:
        return "up", f"{line}, syncing"
    return "up", line


def _with_peers(detail: str, peers: int | None) -> str:
    if peers is None:
        return detail
    noun = "peer" if peers == 1 else "peers"
    return f"{detail} · {peers} {noun}"


def _channel(
    io: ProbeIO,
    payer: str | None,
    payer_state: str,
    network: str,
    peers: int | None,
) -> tuple[str, str]:
    if payer is None:
        return "unknown", "payer container is not running"
    if payer_state == "locked":
        return "locked", "payer wallet locked"
    if payer_state != "up":
        return "unknown", "payer getinfo did not succeed"
    code, raw = io.lncli(payer, network, "listchannels")
    if code != 0:
        return "unknown", _with_peers(scrub(raw) or "listchannels failed", peers)
    count = _active_channels(raw)
    if count is None:
        return "unknown", _with_peers("listchannels was not json", peers)
    if count == 0:
        return "down", _with_peers("no active channel", peers)
    label = "1 active channel" if count == 1 else f"{count} active channels"
    return "up", _with_peers(label, peers)


def _invoice(io: ProbeIO, network: str) -> tuple[str, str]:
    """AWS invoice LND only. A Mac payer does not mark this box up."""
    container = _INVOICE.get(network, _INVOICE["mainnet"])[0]
    try:
        code, raw = io.invoice_getinfo(container, network)
    except Exception:  # noqa: BLE001 — unreachable stays unknown; no exception text
        return "unknown", "AWS invoice LND was not reached"
    if code is None:
        return "unknown", "AWS invoice LND was not reached"
    return _with_height(_classify_getinfo(code, raw))


def _merchant(
    io: ProbeIO,
) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
    """Health and the unpaid challenge are separate. Origin follows health."""
    base = (os.environ.get("DASHBOARD_APERTURE_URL") or "http://127.0.0.1:8081").rstrip(
        "/"
    )
    try:
        health_code, health_err = io.http_status(base + "/health")
    except Exception:  # noqa: BLE001 — health failure must not hide the challenge
        health_code, health_err = None, "health probe failed"
    try:
        hello_code, hello_err = io.http_status(base + "/paid/hello")
    except Exception:  # noqa: BLE001 — a hanging challenge must not mark health down
        hello_code, hello_err = None, "hello probe failed"
    return (
        _health(health_code, health_err),
        _challenge(hello_code, hello_err),
        _origin(health_code),
    )


def _health(code: int | None, err: str) -> tuple[str, str]:
    if code is None:
        return "down", scrub(err) or "health probe failed"
    if code != 200:
        return "down", f"health HTTP {code}"
    return "up", "health 200"


def _challenge(code: int | None, err: str) -> tuple[str, str]:
    if code is None:
        return "down", scrub(err) or "hello probe failed"
    if code == 402:
        return "up", "unpaid hello 402"
    return "down", f"hello HTTP {code}, expected 402"


def _origin(health_code: int | None) -> tuple[str, str]:
    """The origin has no host port. It is up only through Aperture /health."""
    if health_code is None:
        return "unknown", "Aperture was not reached"
    if health_code == 200:
        return "up", "answered through Aperture"
    return "down", f"health HTTP {health_code}"


def _aws_key() -> Path:
    return Path.home() / ".ssh/aws/agent-bitcoin-key.pem"


def _ssh(remote: list[str]) -> subprocess.CompletedProcess[str] | None:
    """One read-only SSH command. The remote args are fixed by the caller."""
    host = _aws_host()
    key = _aws_key()
    if not host or not key.is_file():
        return None
    try:
        return subprocess.run(
            [
                "ssh",
                "-i",
                str(key),
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "StrictHostKeyChecking=yes",
                f"ubuntu@{host}",
                *remote,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _aws_host() -> str:
    """Operator SSH host. Loopback Aperture still uses the lab AWS host."""
    chosen = (os.environ.get("DASHBOARD_AWS_HOST") or "").strip()
    if not chosen:
        base = (os.environ.get("DASHBOARD_APERTURE_URL") or "").strip()
        host = (urlparse(base).hostname or "").lower()
        if host and host not in _LOOPBACK_HOSTS:
            chosen = host
        else:
            chosen = _DEFAULT_AWS_HOST
    if not _HOST_RE.fullmatch(chosen):
        return ""
    return chosen


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

    def invoice_getinfo(self, container: str, network: str) -> tuple[int | None, str]:
        """getinfo on the AWS invoice LND. Unreachable stays an empty code."""
        if container not in _INVOICE_NAMES or network not in _PAYER:
            return None, "AWS invoice LND was not reached"
        done = _ssh(
            [
                "docker",
                "exec",
                container,
                "lncli",
                "--lnddir=/home/lnd/.lnd",
                "--network",
                network,
                "getinfo",
            ]
        )
        if done is None or done.returncode == 255:
            return None, "AWS invoice LND was not reached"
        raw = ((done.stdout or "") + (done.stderr or ""))[:8000]
        return done.returncode, raw

    def chain_info(self, container: str, network: str) -> tuple[int | None, str]:
        """getblockchaininfo. The RPC password stays in the container environment."""
        if _AWS_BITCOIND.get(network) != container:
            return None, ""
        remote = (
            "docker exec "
            + container
            + ' sh -c \'bitcoin-cli -rpcuser="$MAINNET_BITCOIND_RPCUSER" '
            '-rpcpassword="$MAINNET_BITCOIND_RPCPASS" -rpcport=8332 getblockchaininfo\''
        )
        done = _ssh([remote])
        if done is None or done.returncode == 255:
            return None, ""
        return done.returncode, (done.stdout or "")[:8000]

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
        return release_label(root)

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
