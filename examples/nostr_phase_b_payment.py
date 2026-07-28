#!/usr/bin/env python3
"""Phase B: Nostr-signed payment coordination + existing LND invoice/pay.

Infrastructure stays intact:
  - Nostr = signed request / invoice offer / result (identity + coordination)
  - LND  = create_invoice / pay_invoice via docker exec lncli

Typical dual-host regtest (receive-heavy AWS agent):

  # Shared passphrase + bus directory (scp or shared folder)
  export NOSTR_PASSPHRASE='...'
  export NOSTR_POC_DIR=./.nostr-poc

  # 1) Mac (payer has outbound) — or whichever node will PAY
  #    Request an invoice for amount X from the counterparty agent
  LND_PAYER_CONTAINER=agent-bitcoin-lnd \\
    python examples/nostr_phase_b_payment.py request --amount 5000 --memo 'nostr-poc'

  # 2) AWS (invoice / receive) — create bolt11 and publish offer
  #    Copy bus files from Mac first if not shared
  LND_INVOICE_CONTAINER=agent-payment-decision-lnd \\
    python examples/nostr_phase_b_payment.py invoice

  # 3) Mac — pay the offer
  LND_PAYER_CONTAINER=agent-bitcoin-lnd \\
    python examples/nostr_phase_b_payment.py pay

Optional: --decide runs PaymentDecisionAgent before pay (still does not pay itself).

File bus: $NOSTR_POC_DIR/bus/*_{request,offer,result}.json (signed Nostr events).
Public relays are optional and often filter new keys; bus is the reliable lab path.

See docs/nostr-agent-identity.md
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

# Allow running as script from repo root
_EXAMPLES = Path(__file__).resolve().parent
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))

try:
    from pynostr.event import EventKind
except ImportError as e:  # pragma: no cover
    print(
        "Missing pynostr. Use Python 3.12 venv:\n"
        "  uv venv -p 3.12 .venv-nostr\n"
        "  uv pip install --python .venv-nostr/bin/python -e '.[nostr]'\n"
        f"{e}",
        file=sys.stderr,
    )
    sys.exit(1)

from nostr_common import (  # noqa: E402
    COORD_TAG_B,
    load_or_create_agent,
    latest_bus_file,
    parse_payload,
    read_bus_event,
    sign_json_event,
    write_bus_event,
)

DEFAULT_DIR = Path(os.environ.get("NOSTR_POC_DIR", ".nostr-poc")).resolve()
DEFAULT_PASSPHRASE = os.environ.get("NOSTR_PASSPHRASE", "")
DEFAULT_AMOUNT = int(os.environ.get("NOSTR_POC_AMOUNT_SATS", "5000"))

# Dual-host defaults: Mac pays (outbound), AWS agent receives (inbound)
DEFAULT_PAYER_CONTAINER = os.environ.get("LND_PAYER_CONTAINER", "agent-bitcoin-lnd")
DEFAULT_INVOICE_CONTAINER = os.environ.get(
    "LND_INVOICE_CONTAINER", "agent-payment-decision-lnd"
)


def _require_passphrase(p: str) -> str:
    if not p:
        raise SystemExit(
            "Set NOSTR_PASSPHRASE or --passphrase (encrypts Nostr nsec at rest)."
        )
    return p


def _bus_dir(root: Path) -> Path:
    return root / "bus"


def _lnd_client(container: str):
    from agent_bitcoin.lightning import LNDClient

    client = LNDClient()
    client.container = container
    # Both AWS and Mac compose use this lnddir
    client.lnd_dir = os.environ.get("LND_DIR", "/home/lnd/.lnd")
    return client


def cmd_request(args: argparse.Namespace) -> int:
    """Alice (payer agent): publish signed pay_request to the bus."""
    passphrase = _require_passphrase(args.passphrase)
    alice = load_or_create_agent(
        args.dir, "alice", passphrase, force_new=args.force_new_keys
    )
    request_id = args.request_id or uuid.uuid4().hex[:16]
    payload = {
        "type": "pay_request",
        "v": 1,
        "request_id": request_id,
        "amount_sats": args.amount,
        "memo": args.memo,
        "payer_npub": alice.public_key.bech32(),
        "note": "Phase B: counterparty should create an invoice and publish invoice_offer",
    }
    event = sign_json_event(
        alice,
        payload,
        kind=EventKind.TEXT_NOTE,
        tags=[
            ["t", COORD_TAG_B],
            ["client", "agent-bitcoin-phase-b"],
        ],
    )
    if not event.verify():
        raise SystemExit("Failed to verify own pay_request signature")
    path = write_bus_event(_bus_dir(args.dir), f"{request_id}_request.json", event)
    print(f"[request] request_id={request_id}")
    print(f"[request] amount_sats={args.amount} memo={args.memo!r}")
    print(f"[request] bus file: {path}")
    print(
        "\nNext: copy the bus directory to the invoice host (if needed), then:\n"
        f"  LND_INVOICE_CONTAINER={DEFAULT_INVOICE_CONTAINER} \\\n"
        "    python examples/nostr_phase_b_payment.py invoice"
    )
    return 0


def cmd_invoice(args: argparse.Namespace) -> int:
    """Bob (invoice agent): read pay_request, create LND invoice, publish offer."""
    passphrase = _require_passphrase(args.passphrase)
    bob = load_or_create_agent(
        args.dir, "bob", passphrase, force_new=args.force_new_keys
    )
    bus = _bus_dir(args.dir)
    req_path = (
        Path(args.request_file)
        if args.request_file
        else latest_bus_file(bus, "_request.json")
    )
    if not req_path or not req_path.is_file():
        raise SystemExit(f"No pay_request found under {bus}. Run `request` first.")

    req_event = read_bus_event(req_path)
    if not req_event.verify():
        raise SystemExit("pay_request signature invalid")
    req = parse_payload(req_event)
    if req.get("type") != "pay_request":
        raise SystemExit(f"Unexpected message type: {req.get('type')}")

    request_id = req["request_id"]
    amount = int(req["amount_sats"])
    memo = str(req.get("memo") or f"nostr-phase-b-{request_id}")
    print(f"[invoice] verified pay_request from pubkey={req_event.pubkey[:16]}…")
    print(f"[invoice] request_id={request_id} amount_sats={amount}")

    if args.dry_run:
        payment_request = f"lnt_dry_run_{request_id}"
        payment_hash = "00" * 32
        print("[invoice] --dry-run: skipping LND addinvoice")
    else:
        lnd = _lnd_client(args.invoice_container)
        print(f"[invoice] LND container={args.invoice_container}")
        inv = lnd.create_invoice(memo=memo, amount_sats=amount)
        payment_request = inv.payment_request
        payment_hash = inv.payment_hash
        print(f"[invoice] created bolt11 payment_hash={payment_hash}")

    offer = {
        "type": "invoice_offer",
        "v": 1,
        "request_id": request_id,
        "amount_sats": amount,
        "memo": memo,
        "payment_request": payment_request,
        "payment_hash": payment_hash,
        "invoice_npub": bob.public_key.bech32(),
        "in_reply_to_event": req_event.id,
    }
    offer_event = sign_json_event(
        bob,
        offer,
        tags=[
            ["t", COORD_TAG_B],
            ["e", req_event.id or ""],
            ["p", req_event.pubkey or ""],
            ["client", "agent-bitcoin-phase-b"],
        ],
    )
    if not offer_event.verify():
        raise SystemExit("Failed to verify own invoice_offer signature")
    path = write_bus_event(bus, f"{request_id}_offer.json", offer_event)
    print(f"[invoice] bus file: {path}")
    if not args.dry_run:
        # Show truncated bolt11
        pr = payment_request
        print(f"[invoice] payment_request={pr[:40]}…{pr[-20:] if len(pr) > 60 else pr}")
    print(
        "\nNext: copy bus offer back to the payer host (if needed), then:\n"
        f"  LND_PAYER_CONTAINER={DEFAULT_PAYER_CONTAINER} \\\n"
        "    python examples/nostr_phase_b_payment.py pay"
    )
    return 0


def cmd_pay(args: argparse.Namespace) -> int:
    """Alice (payer): verify invoice_offer, optional decide, pay via LND."""
    passphrase = _require_passphrase(args.passphrase)
    alice = load_or_create_agent(args.dir, "alice", passphrase, force_new=False)
    bus = _bus_dir(args.dir)
    offer_path = (
        Path(args.offer_file)
        if args.offer_file
        else latest_bus_file(bus, "_offer.json")
    )
    if not offer_path or not offer_path.is_file():
        raise SystemExit(f"No invoice_offer found under {bus}. Run `invoice` first.")

    offer_event = read_bus_event(offer_path)
    if not offer_event.verify():
        raise SystemExit("invoice_offer signature invalid")
    offer = parse_payload(offer_event)
    if offer.get("type") != "invoice_offer":
        raise SystemExit(f"Unexpected message type: {offer.get('type')}")

    request_id = offer["request_id"]
    amount = int(offer["amount_sats"])
    payment_request = offer["payment_request"]
    print(f"[pay] verified offer from pubkey={offer_event.pubkey[:16]}…")
    print(f"[pay] request_id={request_id} amount_sats={amount}")

    # Ensure offer matches a request we made (if present)
    req_path = bus / f"{request_id}_request.json"
    if req_path.is_file():
        req_event = read_bus_event(req_path)
        req = parse_payload(req_event)
        if req_event.pubkey != alice.public_key.hex():
            print(
                "[pay] WARNING: bus request was not signed by local alice key",
                file=sys.stderr,
            )
        if int(req.get("amount_sats", -1)) != amount:
            raise SystemExit("Offer amount does not match local pay_request")

    if args.decide:
        from agent_bitcoin.agents.payment_decision import PaymentDecisionAgent

        agent = PaymentDecisionAgent()
        decision = agent.decide_payment(
            {
                "amount_sats": amount,
                "payment_request": payment_request,
                "memo": offer.get("memo", ""),
            },
            context="nostr phase-b invoice_offer",
        )
        print(f"[pay] PaymentDecisionAgent => {decision}")
        dec = str(decision.get("decision", "")).upper()
        if dec != "PAY":
            print(f"[pay] STOP: decision is {dec!r}, not PAY")
            return 3

    if args.dry_run or str(payment_request).startswith("lnt_dry_run_"):
        print("[pay] --dry-run or dry invoice: not calling LND payinvoice")
        status = "DRY_RUN"
        payment_hash = offer.get("payment_hash", "")
    else:
        lnd = _lnd_client(args.payer_container)
        print(f"[pay] LND container={args.payer_container}")
        try:
            result = lnd.pay_invoice(payment_request)
            status = getattr(result, "status", None) or str(result)
            payment_hash = getattr(result, "payment_hash", "") or offer.get(
                "payment_hash", ""
            )
            print(
                f"[pay] LND result success={getattr(result, 'success', None)} "
                f"status={status} amount={getattr(result, 'amount', None)} "
                f"payment_hash={payment_hash}"
            )
        except Exception as exc:
            # Payment may have succeeded on-chain even if response parsing failed
            print(f"[pay] LND pay raised: {exc}", file=sys.stderr)
            print(
                "[pay] Check whether funds already moved, e.g.:\n"
                "  docker compose -f docker-compose.regtest.mac.yml exec -T "
                "agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd "
                "--network=regtest listpayments | tail -40",
                file=sys.stderr,
            )
            status = f"ERROR: {exc}"
            payment_hash = offer.get("payment_hash", "")

    result_payload = {
        "type": "payment_result",
        "v": 1,
        "request_id": request_id,
        "status": str(status),
        "payment_hash": payment_hash,
        "amount_sats": amount,
        "payer_npub": alice.public_key.bech32(),
    }
    result_event = sign_json_event(
        alice,
        result_payload,
        tags=[
            ["t", COORD_TAG_B],
            ["e", offer_event.id or ""],
            ["client", "agent-bitcoin-phase-b"],
        ],
    )
    path = write_bus_event(bus, f"{request_id}_result.json", result_event)
    print(f"[pay] bus file: {path}")
    print("\nRESULT: Phase B coordination complete.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    bus = _bus_dir(args.dir)
    print(f"key dir: {args.dir}")
    print(f"bus dir: {bus}")
    if not bus.is_dir():
        print("(empty)")
        return 0
    for p in sorted(bus.glob("*.json")):
        try:
            ev = read_bus_event(p)
            payload = parse_payload(ev)
            print(
                f"  {p.name}: type={payload.get('type')} "
                f"request_id={payload.get('request_id')} "
                f"verified_sig=yes"
            )
        except Exception as exc:
            print(f"  {p.name}: ERROR {exc}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Phase B: Nostr-signed pay request/offer + LND invoice/pay"
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"Nostr key + bus root (default {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--passphrase",
        default=DEFAULT_PASSPHRASE,
        help="Nostr nsec encryption passphrase (or NOSTR_PASSPHRASE)",
    )
    parser.add_argument(
        "--force-new-keys",
        action="store_true",
        help="Regenerate alice/bob Nostr keys",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_req = sub.add_parser("request", help="Sign pay_request (payer agent)")
    p_req.add_argument("--amount", type=int, default=DEFAULT_AMOUNT)
    p_req.add_argument("--memo", default="agent-bitcoin nostr phase-b")
    p_req.add_argument("--request-id", default="")
    p_req.set_defaults(func=cmd_request)

    p_inv = sub.add_parser("invoice", help="Create LND invoice + sign offer")
    p_inv.add_argument(
        "--invoice-container",
        default=DEFAULT_INVOICE_CONTAINER,
        help="Docker LND that creates the invoice (default: agent-payment-decision-lnd)",
    )
    p_inv.add_argument("--request-file", default="")
    p_inv.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call LND; write a fake offer for protocol testing",
    )
    p_inv.set_defaults(func=cmd_invoice)

    p_pay = sub.add_parser("pay", help="Verify offer and pay via LND")
    p_pay.add_argument(
        "--payer-container",
        default=DEFAULT_PAYER_CONTAINER,
        help="Docker LND that pays (default: agent-bitcoin-lnd on Mac)",
    )
    p_pay.add_argument("--offer-file", default="")
    p_pay.add_argument(
        "--decide",
        action="store_true",
        help="Run PaymentDecisionAgent before paying",
    )
    p_pay.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call LND payinvoice",
    )
    p_pay.set_defaults(func=cmd_pay)

    p_st = sub.add_parser("status", help="List bus messages")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    print("=== agent-bitcoin Nostr Phase B (coordination + LND) ===")
    print(f"dir={args.dir}")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
