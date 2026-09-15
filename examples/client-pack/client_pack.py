#!/usr/bin/env python3
"""Ubuntu trial CLI for the L402 client pack. Local Neutrino LND only.

Does not: AWS API, auto-POST hello, print seeds, open 8081, use Mac/AWS invoice LND.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Callable

PACK = Path(__file__).resolve().parent
ROOT = PACK.parents[1]
COMPOSE = PACK / "docker-compose.yml"
HELLO = PACK / "client-hello.json"
CONTAINER = "l402-client-lnd"
WALLET_DB = "/home/lnd/.lnd/data/chain/bitcoin/mainnet/wallet.db"
AWS_PEER = (
    "0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967"
    "@3.90.159.146:9735"
)
AWS_PUB = AWS_PEER.split("@", 1)[0]
L402_URL = "http://3.90.159.146:8081/paid/finance/mempool-feerate"
FEEURL = "https://nodes.lightning.computer/fees/v1/btc-fee-estimates.json"
MIN_FUND_SATS = 50_000

LncliFn = Callable[..., Any]


def lncli(*args: str, check: bool = True) -> str:
    cmd = [
        "docker",
        "exec",
        CONTAINER,
        "lncli",
        "--lnddir=/home/lnd/.lnd",
        "--network=mainnet",
        *args,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if check and proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "lncli failed")
    return proc.stdout


def lncli_json(*args: str) -> dict[str, Any]:
    return json.loads(lncli(*args))


def detect_ip() -> str:
    override = (os.environ.get("MY_IP") or "").strip()
    if override:
        return override
    for url in (
        "https://checkip.amazonaws.com",
        "https://ifconfig.me",
    ):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                ip = resp.read().decode().strip()
            if ip.count(".") == 3 and all(p.isdigit() for p in ip.split(".")):
                return ip
        except OSError:
            continue
    raise SystemExit("Could not detect public IPv4. Set MY_IP=x.x.x.x")


def cmd_doctor(_args: argparse.Namespace) -> int:
    print("=== doctor ===")
    py = sys.version_info
    print(f"Python: {py.major}.{py.minor}.{py.micro} ({sys.executable})")
    if (py.major, py.minor) != (3, 12):
        print(
            "Hint: use python3.12 for this trial (do not sudo-install Docker from here)."
        )
    docker = shutil.which("docker")
    print(
        f"docker: {docker or 'MISSING — install Docker yourself; this command will not sudo.'}"
    )
    if not COMPOSE.is_file():
        raise SystemExit(f"missing {COMPOSE}")
    text = COMPOSE.read_text(encoding="utf-8")
    if FEEURL not in text:
        raise SystemExit("compose missing Neutrino --feeurl")
    if "127.0.0.1:10009:10009" not in text:
        raise SystemExit("compose must bind gRPC to 127.0.0.1:10009 only")
    if "0.0.0.0/0" in text:
        raise SystemExit("compose must not use 0.0.0.0/0")
    print(f"compose: {COMPOSE} (feeurl ok, gRPC localhost)")
    print(f"container: {CONTAINER}")
    return 0 if docker else 1


def cmd_up(_args: argparse.Namespace) -> int:
    (PACK / "data" / "lnd").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "up", "-d"],
        cwd=str(PACK),
        check=True,
    )
    print("compose up:", CONTAINER)
    return 0


def _wallet_exists() -> bool:
    proc = subprocess.run(
        ["docker", "exec", CONTAINER, "test", "-f", WALLET_DB],
        check=False,
    )
    return proc.returncode == 0


def cmd_wallet(_args: argparse.Namespace) -> int:
    if not _wallet_exists():
        if not sys.stdin.isatty():
            raise SystemExit(
                "No wallet.db. On a TTY run: docker exec -it "
                f"{CONTAINER} lncli --lnddir=/home/lnd/.lnd --network=mainnet create\n"
                "Do not paste the seed into chat, git, or AWS."
            )
        print("Creating wallet on THIS machine (seed stays here; not logged).")
        subprocess.run(
            [
                "docker",
                "exec",
                "-it",
                CONTAINER,
                "lncli",
                "--lnddir=/home/lnd/.lnd",
                "--network=mainnet",
                "create",
            ],
            check=False,
        )
        if not _wallet_exists():
            raise SystemExit("wallet create did not produce wallet.db")
    try:
        lncli_json("getinfo")
        print("wallet unlocked")
        return 0
    except SystemExit:
        pass
    pw = Path(os.environ.get("WALLET_PASSWORD_FILE") or (PACK / ".wallet-password"))
    if pw.is_file():
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER,
                "lncli",
                "--lnddir=/home/lnd/.lnd",
                "--network=mainnet",
                "unlock",
            ],
            stdin=pw.open("rb"),
            check=False,
        )
    elif sys.stdin.isatty():
        subprocess.run(
            [
                "docker",
                "exec",
                "-it",
                CONTAINER,
                "lncli",
                "--lnddir=/home/lnd/.lnd",
                "--network=mainnet",
                "unlock",
            ],
            check=False,
        )
    try:
        lncli_json("getinfo")
        print("wallet unlocked")
        return 0
    except SystemExit:
        raise SystemExit("wallet locked. Unlock on a TTY with lncli unlock.") from None


def write_hello(ip: str, pub: str, path: Path = HELLO) -> dict[str, str]:
    doc = {
        "egress_ip": ip,
        "identity_pubkey": pub,
        "l402_host": "http://3.90.159.146:8081",
    }
    for bad in ("seed", "macaroon", "password", "nsec"):
        if bad in doc:
            raise SystemExit("refusing to write secrets")
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def cmd_hello(_args: argparse.Namespace) -> int:
    info = lncli_json("getinfo")
    pub = str(info["identity_pubkey"])
    ip = detect_ip()
    write_hello(ip, pub)
    print(f"Wrote {HELLO} (IP + pubkey only — send this to the operator)")
    print("Connecting to AWS LND (outbound)…")
    proc = subprocess.run(
        [
            "docker",
            "exec",
            CONTAINER,
            "lncli",
            "--lnddir=/home/lnd/.lnd",
            "--network=mainnet",
            "connect",
            AWS_PEER,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(
            f"connect: already connected or AWS 9735 not yet allowlisted for {ip}/32",
            file=sys.stderr,
        )
    return 0


def channel_status_rows(
    channels: list[dict[str, Any]] | None,
    *,
    aws_pub: str = AWS_PUB,
) -> list[dict[str, Any]]:
    """Summarize channels for status. Prefer the AWS peer if present."""
    chans = list(channels or [])
    aws = [c for c in chans if str(c.get("remote_pubkey") or "") == aws_pub]
    use = aws if aws else chans
    rows: list[dict[str, Any]] = []
    for c in use:
        local = int(c.get("local_balance") or 0)
        reserve = int(c.get("local_chan_reserve_sat") or 0)
        rows.append(
            {
                "remote_pubkey": str(c.get("remote_pubkey") or ""),
                "active": c.get("active"),
                "private": c.get("private"),
                "local_balance": local,
                "remote_balance": int(c.get("remote_balance") or 0),
                "local_chan_reserve_sat": reserve,
                "approx_spendable": max(0, local - reserve),
                "total_satoshis_sent": int(c.get("total_satoshis_sent") or 0),
            }
        )
    return rows


def cmd_status(_args: argparse.Namespace) -> int:
    info = lncli_json("getinfo")
    bal = lncli_json("walletbalance")
    chans = lncli_json("listchannels")
    all_ch = chans.get("channels") or []
    print("synced_to_chain:", info.get("synced_to_chain"))
    print("num_peers:", info.get("num_peers"))
    print("on-chain confirmed_balance:", bal.get("confirmed_balance"))
    print("num_channels:", len(all_ch))
    rows = channel_status_rows(all_ch)
    if not rows:
        print("channels: none")
        return 0
    for i, row in enumerate(rows, 1):
        pub = row["remote_pubkey"]
        tag = " AWS" if pub == AWS_PUB else ""
        print(f"channel {i}{tag} remote={pub[:16]}…")
        print("  active:", row["active"])
        print("  private:", row["private"])
        print("  local_balance:", row["local_balance"])
        print("  remote_balance:", row["remote_balance"])
        print("  local_chan_reserve_sat:", row["local_chan_reserve_sat"])
        print("  approx_spendable:", row["approx_spendable"])
        print("  total_satoshis_sent:", row["total_satoshis_sent"])
    return 0


def cmd_address(_args: argparse.Namespace) -> int:
    addr = lncli_json("newaddress", "p2wkh")["address"]
    print(addr)
    print(
        f"Fund this address with at least ~{MIN_FUND_SATS} sats "
        "(channel + miner fee). Do not send only 1000 sats."
    )
    return 0


def cmd_open(
    args: argparse.Namespace,
    *,
    balance_fn: Callable[[], dict[str, Any]] | None = None,
    open_fn: Callable[..., str] | None = None,
) -> int:
    sats = int(args.sats)
    if sats <= 0:
        raise SystemExit("--sats must be positive")
    bal = (balance_fn or (lambda: lncli_json("walletbalance")))()
    confirmed = int(bal.get("confirmed_balance") or 0)
    if confirmed <= 0 or confirmed < sats:
        print(
            f"Refuse open: confirmed_balance={confirmed} "
            f"(need {sats}+). Use address, fund ≥ ~{MIN_FUND_SATS} sats, wait for confirm.",
            file=sys.stderr,
        )
        return 4
    print(f"Opening PRIVATE channel {sats} sats to {AWS_PUB}")
    runner = open_fn or lncli
    runner(
        "openchannel",
        "--private",
        f"--node_key={AWS_PUB}",
        f"--local_amt={sats}",
    )
    return 0


def cmd_smoke(_args: argparse.Namespace) -> int:
    env = os.environ.copy()
    env.update(
        {
            "LND_NETWORK": "mainnet",
            "LND_CONTAINER": CONTAINER,
            "LND_TRANSPORT": "docker",
            "AGENT_BITCOIN_ALLOW_MAINNET": "1",
            "AGENT_BITCOIN_ALLOW_AUTOPAY": "1",
        }
    )
    pay = ROOT / "examples" / "l402_pay.py"
    cmd = [sys.executable, str(pay), "--url", L402_URL, "--price", "100"]
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def cmd_all(args: argparse.Namespace) -> int:
    for fn in (cmd_doctor, cmd_up, cmd_wallet, cmd_hello):
        code = fn(args)
        if code:
            return code
    print(
        "Stop here. Send client-hello.json to the operator "
        "(they add your /32 on 8081 and 9735). "
        "Then: address → fund → open --sats → smoke."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="client_pack.py",
        description="Ubuntu L402 client pack (local Neutrino LND). No AWS API.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor", help="check docker/python/compose (no sudo install)")
    sub.add_parser("up", help="docker compose up -d")
    sub.add_parser("wallet", help="create/unlock local wallet on TTY")
    sub.add_parser("hello", help="write client-hello.json and connect to AWS")
    sub.add_parser("status", help="getinfo / balance / channels")
    sub.add_parser("address", help="new on-chain address; fund ≥ ~50k sats")
    op = sub.add_parser("open", help="private openchannel to AWS (after fund)")
    op.add_argument("--sats", type=int, required=True)
    sub.add_parser("smoke", help="100-sat GET mempool-feerate via l402_pay.py")
    sub.add_parser("all", help="doctor → up → wallet → hello, then stop")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "doctor": cmd_doctor,
        "up": cmd_up,
        "wallet": cmd_wallet,
        "hello": cmd_hello,
        "status": cmd_status,
        "address": cmd_address,
        "open": cmd_open,
        "smoke": cmd_smoke,
        "all": cmd_all,
    }
    return int(handlers[args.cmd](args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
