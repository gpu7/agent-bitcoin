"""Read-only probes for the Mac infrastructure map.

Allowed LND commands are getinfo and listchannels. The invoice agent is the
AWS LND, reached over the operator SSH path. listchannels runs on the Mac
payer and on that AWS LND. AWS chain progress is getblockchaininfo on the
AWS bitcoind container. Nothing here unlocks a wallet, pays an invoice, or
opens a channel.
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
_MAC_NODE_PUBKEY = "0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967"
_CHANNEL_DETAIL_LIMIT = 4000


class CommandRejected(RuntimeError):
    """A probe asked for a command this dashboard does not run."""


def scrub(text: str, limit: int = 140, *, keep_blank: bool = False) -> str:
    """Drop secrets. Spaces on each line collapse. Line breaks stay."""
    cleaned = _SECRET_RE.sub("[redacted]", text or "")
    lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    if not keep_blank:
        lines = [line for line in lines if line]
    cleaned = "\n".join(lines)
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
    detail_limit: int = 140
    keep_blank: bool = False

    def as_dict(self) -> dict[str, str]:
        payload = {
            "id": self.id,
            "label": self.label,
            "state": self.state,
            "detail": scrub(
                self.detail, limit=self.detail_limit, keep_blank=self.keep_blank
            ),
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

    def invoice_listchannels(
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
    return info.state, f"{info.detail}\nheight: {info.block_height}"


def chain_progress_line(data: dict[str, object]) -> str | None:
    """Three labeled lines. Missing fields do not become a guess."""
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
    return f"blocks: {blocks}\nheaders: {headers}\nprogress: {percent}%"


def _sat_amount(value: object) -> int | None:
    """Sats from lncli: a non-negative int, or a decimal string of one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str) and value.isascii() and value.isdigit():
        amount = int(value)
    else:
        return None
    if amount < 0:
        return None
    return amount


def _channel_rows(raw: str) -> list[dict[str, object]] | None:
    """Every channel object. A missing active flag is still a row."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    channels = data.get("channels")
    if not isinstance(channels, list):
        return None
    return [ch for ch in channels if isinstance(ch, dict)]


def _alias_text(row: dict[str, object]) -> str | None:
    """Non-empty peer alias. A 32-hex alias would be redacted, so it is skipped."""
    for key in ("peer_alias", "alias"):
        value = row.get(key)
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text or not text.isascii():
            continue
        if any(ord(char) < 32 or ord(char) > 126 for char in text):
            continue
        if len(text) >= 32 and all(char in "0123456789abcdefABCDEF" for char in text):
            continue
        return text[:32]
    return None


def _peer_label(row: dict[str, object]) -> str:
    """Mac for the known payer pubkey, then the alias, then the last 8 hex."""
    pubkey = row.get("remote_pubkey")
    if isinstance(pubkey, str) and pubkey.strip().lower() == _MAC_NODE_PUBKEY:
        return "Mac"
    alias = _alias_text(row)
    if alias is not None:
        return alias
    if isinstance(pubkey, str):
        hex_key = pubkey.strip().lower()
        if len(hex_key) >= 8 and all(char in "0123456789abcdef" for char in hex_key):
            return hex_key[-8:]
    return "peer"


def _channel_line(side: str, row: dict[str, object]) -> str:
    """One channel block. local is outbound and remote is inbound."""
    status = "Active" if row.get("active") is True else "Inactive"
    lines = [f"{side}: {_peer_label(row)}", status]
    amounts = (
        ("Capacity", _sat_amount(row.get("capacity"))),
        ("Outbound", _sat_amount(row.get("local_balance"))),
        ("Inbound", _sat_amount(row.get("remote_balance"))),
    )
    for name, amount in amounts:
        if amount is not None:
            lines.append(f"{name}: {amount} sats")
    return "\n".join(lines)


def _side_lines(
    side: str, code: int | None, raw: str
) -> tuple[list[str], list[dict[str, object]] | None]:
    """Lines for one LND. None rows means that probe failed."""
    if code is None:
        return [f"{side} listchannels was not reached"], None
    if code != 0:
        return [f"{side} listchannels failed"], None
    rows = _channel_rows(raw)
    if rows is None:
        return [f"{side} listchannels was not json"], None
    return [_channel_line(side, row) for row in rows], rows


def collect_status(io: ProbeIO, *, network: str | None = None) -> dict[str, object]:
    """Build the map. A failed probe stays failed; nothing is marked up by default."""
    net = network or network_name()
    names = io.containers()
    payer = _first_running(names, _PAYER.get(net, _PAYER["regtest"]))

    payer_info = _lnd_node(io, payer, net, "payer container is not running")
    payer_state, payer_detail = _with_height(payer_info)
    invoice_state, invoice_detail = _invoice(io, net)
    bitcoin = _bitcoin(io, net)
    channel = _channel(io, payer, payer_state, net)
    aperture, challenge, origin = _merchant(io)
    nostr = _nostr(io)

    nodes = [
        Node("bitcoin", "Bitcoin network", *bitcoin),
        Node(
            "channel",
            "Lightning channels",
            channel[0],
            channel[1],
            detail_limit=_CHANNEL_DETAIL_LIMIT,
            keep_blank=True,
        ),
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


def _channel(
    io: ProbeIO,
    payer: str | None,
    payer_state: str,
    network: str,
) -> tuple[str, str]:
    """Every Mac channel, then every AWS channel."""
    lines: list[str] = []
    mac_rows: list[dict[str, object]] | None = None
    if payer is None:
        lines.append("payer container is not running")
    elif payer_state == "locked":
        lines.append("payer wallet locked")
    elif payer_state != "up":
        lines.append("payer getinfo did not succeed")
    else:
        code, raw = io.lncli(payer, network, "listchannels")
        mac_lines, mac_rows = _side_lines("Mac", code, raw)
        lines.extend(mac_lines)

    container = _INVOICE.get(network, _INVOICE["mainnet"])[0]
    try:
        aws_code, aws_raw = io.invoice_listchannels(container, network)
    except Exception:  # noqa: BLE001 — AWS failure must not hide Mac channels
        aws_code, aws_raw = None, ""
    aws_lines, aws_rows = _side_lines("AWS", aws_code, aws_raw)
    lines.extend(aws_lines)

    shown: list[dict[str, object]] = []
    if mac_rows is not None:
        shown.extend(mac_rows)
    if aws_rows is not None:
        shown.extend(aws_rows)
    any_active = any(row.get("active") is True for row in shown)
    any_list = mac_rows is not None or aws_rows is not None
    if mac_rows == [] and aws_rows == [] and payer_state == "up":
        lines = ["no channels"]

    if payer_state == "locked":
        state = "locked"
    elif any_active:
        state = "up"
    elif any_list:
        state = "down"
    else:
        state = "unknown"
    return state, "\n\n".join(lines)


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
        return "up", "unpaid hello: 402"
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
            return "up", f"{host}: 443\naccepted a connection"
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

    def invoice_listchannels(
        self, container: str, network: str
    ) -> tuple[int | None, str]:
        """listchannels on the AWS invoice LND. Same SSH path as getinfo."""
        if container not in _INVOICE_NAMES or network not in _PAYER:
            return None, "AWS listchannels was not reached"
        done = _ssh(
            [
                "docker",
                "exec",
                container,
                "lncli",
                "--lnddir=/home/lnd/.lnd",
                "--network",
                network,
                "listchannels",
            ]
        )
        if done is None or done.returncode == 255:
            return None, "AWS listchannels was not reached"
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
