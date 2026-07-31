#!/usr/bin/env python3
"""
Signet product-path smoke: create or pay invoices via the SDK (no lncli typing).

Must run on the host that can `docker exec` the target LND container.

Typical dual-node flow (AWS has most channel liquidity):
  Mac:  LND_CONTAINER=agent-bitcoin-lnd-signet  create
  AWS:  LND_CONTAINER=agent-payment-decision-lnd-signet  pay --bolt11 'lntbs...'

Usage:
  export LND_NETWORK=signet
  export LND_CONTAINER=agent-bitcoin-lnd-signet   # or AWS signet container
  export LND_DIR=/home/lnd/.lnd

  uv run python examples/signet_product_path.py create [--memo TEXT] [--amount 2000]
  uv run python examples/signet_product_path.py pay --bolt11 'lntbs...'
  uv run python examples/signet_product_path.py balance
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Allow `uv run python examples/...` even if the project is not installed editable
# (e.g. older checkouts missing [build-system] in pyproject.toml).
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _require_signet() -> None:
    network = os.getenv("LND_NETWORK", "").strip().lower()
    if network != "signet":
        print(
            "ERROR: set LND_NETWORK=signet (refusing other networks for this smoke).",
            file=sys.stderr,
        )
        sys.exit(1)
    if os.getenv("AGENT_BITCOIN_ALLOW_MAINNET") == "1" and network == "mainnet":
        print("ERROR: mainnet not allowed for this example.", file=sys.stderr)
        sys.exit(1)


def _require_container() -> str:
    container = (os.getenv("LND_CONTAINER") or "").strip()
    if not container:
        print(
            "ERROR: set LND_CONTAINER "
            "(e.g. agent-bitcoin-lnd-signet or agent-payment-decision-lnd-signet).",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        r = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                container,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: docker not found on this host.", file=sys.stderr)
        sys.exit(1)
    if r.returncode != 0 or r.stdout.strip() != "true":
        print(
            f"ERROR: container {container!r} is not running on this host.\n"
            "  SDK uses local docker exec — run create on Mac for Mac LND, "
            "pay on AWS for AWS LND.",
            file=sys.stderr,
        )
        sys.exit(1)
    return container


def cmd_create(args: argparse.Namespace) -> int:
    _require_signet()
    container = _require_container()
    from agent_bitcoin import create_client

    client = create_client()
    inv = client.create_invoice(
        memo=args.memo,
        amount_sats=args.amount,
        expiry_seconds=args.expiry,
    )
    print(f"container={container}")
    print(f"network={os.environ.get('LND_NETWORK')}")
    print(f"amount_sats={args.amount}")
    print(f"r_hash={inv.r_hash}")
    print(f"payment_request={inv.payment_request}")
    out = Path(args.out) if args.out else Path("/tmp/signet-bolt11.txt")
    out.write_text(inv.payment_request + "\n", encoding="utf-8")
    print(f"wrote={out}")
    print("")
    print("Next (AWS payer) — prefer file so the terminal cannot wrap the bolt11:")
    print("  # copy file to AWS, e.g.:")
    print(f"  #   scp {out} ubuntu@<AWS_EIP>:/tmp/signet-bolt11.txt")
    print(
        "  export LND_NETWORK=signet LND_CONTAINER=agent-payment-decision-lnd-signet LND_DIR=/home/lnd/.lnd"
    )
    print(
        "  uv run python examples/signet_product_path.py pay --file /tmp/signet-bolt11.txt"
    )
    return 0


def _normalize_bolt11(raw: str) -> str:
    """Strip whitespace/newlines from pasted BOLT11 (terminal wrap often inserts them)."""
    return "".join(raw.split())


def _load_bolt11(args: argparse.Namespace) -> str:
    if getattr(args, "file", None):
        path = Path(args.file)
        if not path.is_file():
            print(f"ERROR: bolt11 file not found: {path}", file=sys.stderr)
            sys.exit(1)
        return _normalize_bolt11(path.read_text(encoding="utf-8"))
    if args.bolt11 == "-" or (
        not args.bolt11 and not os.getenv("BOLT11") and not sys.stdin.isatty()
    ):
        return _normalize_bolt11(sys.stdin.read())
    return _normalize_bolt11(args.bolt11 or os.getenv("BOLT11") or "")


def cmd_pay(args: argparse.Namespace) -> int:
    _require_signet()
    container = _require_container()
    bolt11 = _load_bolt11(args)
    if not bolt11:
        print(
            "ERROR: pass --file PATH, --bolt11 STR, BOLT11 env, or pipe stdin.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not bolt11.startswith("ln"):
        print(
            f"ERROR: bolt11 does not look like an invoice (prefix={bolt11[:8]!r}).",
            file=sys.stderr,
        )
        sys.exit(1)
    from agent_bitcoin import create_client

    client = create_client()
    result = client.pay_invoice(bolt11)
    print(f"container={container}")
    print(f"success={result.success}")
    print(f"status={result.status}")
    print(f"payment_hash={result.payment_hash}")
    print(f"amount={result.amount}")
    return 0 if result.success else 1


def cmd_balance(_args: argparse.Namespace) -> int:
    _require_signet()
    container = _require_container()
    from agent_bitcoin import create_client

    client = create_client()
    ch = client.get_channel_balance()
    print(f"container={container}")
    print(f"local_balance={ch.local_balance}")
    print(f"remote_balance={ch.remote_balance}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Signet product-path smoke (SDK create/pay/balance)."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create", help="Create invoice via SDK")
    p_create.add_argument("--memo", default="signet-sdk-product")
    p_create.add_argument("--amount", type=int, default=2000)
    p_create.add_argument("--expiry", type=int, default=3600)
    p_create.add_argument(
        "--out",
        default="/tmp/signet-bolt11.txt",
        help="Write payment_request to this file (default: /tmp/signet-bolt11.txt)",
    )
    p_create.set_defaults(func=cmd_create)

    p_pay = sub.add_parser("pay", help="Pay bolt11 via SDK")
    p_pay.add_argument(
        "--bolt11",
        default="",
        help="BOLT11 string, or '-' to read stdin; also BOLT11 env",
    )
    p_pay.add_argument(
        "--file",
        default="",
        help="Read BOLT11 from file (preferred; survives terminal wrap)",
    )
    p_pay.set_defaults(func=cmd_pay)

    p_bal = sub.add_parser("balance", help="Channel balance via SDK")
    p_bal.set_defaults(func=cmd_balance)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
