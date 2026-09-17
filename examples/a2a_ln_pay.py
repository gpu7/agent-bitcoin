#!/usr/bin/env python3
"""Agent-to-agent Lightning: two LND nodes, one 100-sat invoice, one pay.

This is NOT the swarm (Alice/Bob sharing one Mac wallet). Two containers:

  Payee: agent-payment-decision-lnd-mainnet  (AWS)
  Payer: agent-bitcoin-lnd-mainnet           (Mac)
         or l402-client-lnd                  (Ubuntu client pack)

Invoice on the payee host; pay on the payer host. Same mainnet latches as L402.
Optional encrypted Nostr DM (NIP-17 gift wrap) so you do not SSH-paste BOLT11.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from agent_bitcoin import create_client
from agent_bitcoin.models import Invoice, PaymentResult

DEFAULT_SATS = 100
DEFAULT_RELAYS = "wss://relay.damus.io,wss://nos.lol"
DEFAULT_WAIT = 60
_EXAMPLES = Path(__file__).resolve().parent
if str(_EXAMPLES) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES))


def _require_latches(*, pay: bool) -> None:
    net = (os.environ.get("LND_NETWORK") or "").strip().lower()
    if net != "mainnet":
        return
    if os.environ.get("AGENT_BITCOIN_ALLOW_MAINNET") != "1":
        raise SystemExit("Mainnet: set AGENT_BITCOIN_ALLOW_MAINNET=1")
    if pay and os.environ.get("AGENT_BITCOIN_ALLOW_AUTOPAY") != "1":
        raise SystemExit("Mainnet pay: set AGENT_BITCOIN_ALLOW_AUTOPAY=1")


def _relays() -> list[str]:
    raw = (os.environ.get("NOSTR_RELAYS") or DEFAULT_RELAYS).strip()
    return [u.strip() for u in raw.split(",") if u.strip()]


def _passphrase() -> str:
    p = (os.environ.get("NOSTR_PASSPHRASE") or "").strip()
    if not p:
        raise SystemExit("Set NOSTR_PASSPHRASE (encrypts nsec at rest).")
    return p


def _poc_dir() -> Path:
    return Path(os.environ.get("NOSTR_POC_DIR", ".nostr-poc")).resolve()


def npub_to_hex(npub: str) -> str:
    from bech32 import bech32_decode, convertbits

    hrp, data = bech32_decode((npub or "").strip())
    if hrp != "npub" or not data:
        raise SystemExit("bad npub")
    raw = bytes(convertbits(data, 5, 8, False) or b"")
    if len(raw) != 32:
        raise SystemExit("bad npub length")
    return raw.hex()


def build_invoice_payload(sats: int, bolt11: str, expiry_unix: int) -> dict[str, Any]:
    return {
        "v": 1,
        "type": "a2a_invoice",
        "sats": int(sats),
        "bolt11": bolt11,
        "expiry_unix": int(expiry_unix),
    }


def check_invoice_payload(
    payload: dict[str, Any],
    expected_sats: int,
    *,
    now: int | None = None,
    decoded: dict[str, Any] | None = None,
) -> str:
    if payload.get("type") != "a2a_invoice":
        raise ValueError("not a2a_invoice")
    if int(payload.get("sats") or 0) != int(expected_sats):
        raise ValueError("wrong sats")
    now_i = int(now if now is not None else time.time())
    exp = int(payload.get("expiry_unix") or 0)
    if exp and exp < now_i:
        raise ValueError("expired")
    bolt11 = str(payload.get("bolt11") or "")
    if not bolt11.lower().startswith("ln"):
        raise ValueError("bad bolt11")
    if decoded:
        try:
            amt = int(decoded.get("num_satoshis") or decoded.get("num_sats") or 0)
        except (TypeError, ValueError):
            amt = 0
        if amt and amt != int(expected_sats):
            raise ValueError("bolt11 amount mismatch")
    return bolt11


def wrap_payload(
    sk: Any, to_pubkey_hex: str, payload: dict[str, Any]
) -> dict[str, Any]:
    from agent_bitcoin.nostr.nip17 import gift_wrap

    return gift_wrap(
        sk, to_pubkey_hex, json.dumps(payload, separators=(",", ":"), sort_keys=True)
    )


def unwrap_payload(
    sk: Any, wrap: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    from agent_bitcoin.nostr.nip17 import gift_unwrap

    rumor = gift_unwrap(sk, wrap)
    return json.loads(rumor["content"]), rumor


def cmd_invoice(args: argparse.Namespace, client: Any | None = None) -> int:
    if args.offline:
        print("OFFLINE invoice sats=100 payment_request=lnbc1offline…")
        return 0
    _require_latches(pay=False)
    c = client or create_client()
    inv: Invoice = c.create_invoice(
        memo=args.memo, amount_sats=int(args.sats), expiry_seconds=3600
    )
    bolt = inv.payment_request
    shown = bolt if len(bolt) < 24 else bolt[:16] + "…"
    print(f"invoice sats={args.sats} payment_hash={inv.payment_hash}")
    print(f"payment_request_prefix={shown}")
    print(inv.payment_request)
    print("Pay this BOLT11 on the PAYER node (different LND_CONTAINER).")
    return 0


def cmd_pay(args: argparse.Namespace, client: Any | None = None) -> int:
    bolt11 = (args.bolt11 or "").strip()
    if not bolt11:
        raise SystemExit("--bolt11 is required")
    if args.offline:
        print("OFFLINE pay SUCCEEDED payment_hash=deadbeef preimage=cafef00d")
        return 0
    _require_latches(pay=True)
    c = client or create_client()
    result: PaymentResult = c.pay_invoice(bolt11)
    print(
        f"pay success={result.success} status={result.status} "
        f"amount={result.amount} payment_hash={result.payment_hash} "
        f"preimage={result.preimage}"
    )
    container = os.environ.get("LND_CONTAINER") or "agent-bitcoin-lnd-mainnet"
    network = os.environ.get("LND_NETWORK") or "mainnet"
    print(
        "Check: docker exec "
        f"{container} lncli --lnddir=/home/lnd/.lnd --network={network} "
        "listpayments --max_payments 3"
    )
    return 0 if result.success else 1


def _load_nostr(name: str) -> Any:
    from nostr_common import load_or_create_agent

    return load_or_create_agent(_poc_dir(), name, _passphrase())


def _publish_wrap(wrap: dict[str, Any], relays: list[str]) -> None:
    from pynostr.event import Event
    from pynostr.relay_manager import RelayManager

    ev = Event(
        content=wrap["content"],
        kind=int(wrap["kind"]),
        tags=wrap.get("tags") or [],
        pubkey=wrap.get("pubkey"),
    )
    ev.id = wrap.get("id")
    ev.created_at = wrap.get("created_at")
    ev.sig = wrap.get("sig")
    mgr = RelayManager(timeout=8)
    for url in relays:
        mgr.add_relay(url, timeout=3, close_on_eose=True)
    mgr.publish_event(ev)
    mgr.run_sync()
    mgr.close_all_relay_connections()


def cmd_invoice_dm(args: argparse.Namespace, client: Any | None = None) -> int:
    sats = int(args.sats)
    if args.offline:
        print("sent (offline, no relay, no LND)")
        return 0
    to_hex = npub_to_hex(args.to_npub)
    _require_latches(pay=False)
    c = client or create_client()
    inv: Invoice = c.create_invoice(
        memo=args.memo, amount_sats=sats, expiry_seconds=3600
    )
    expiry_unix = int(time.time()) + 3600
    payload = build_invoice_payload(sats, inv.payment_request, expiry_unix)
    sk = _load_nostr(args.nostr_name)
    wrap = wrap_payload(sk, to_hex, payload)
    _publish_wrap(wrap, _relays())
    print("sent")
    return 0


def _poll_dm(
    sk: Any,
    from_hex: str,
    expected_sats: int,
    wait_s: float,
    *,
    inbox: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    deadline = time.time() + wait_s
    if inbox is not None:
        for wrap in inbox:
            try:
                payload, rumor = unwrap_payload(sk, wrap)
            except (ValueError, json.JSONDecodeError, TypeError, KeyError):
                continue
            if str(rumor.get("pubkey") or "") != from_hex:
                continue
            check_invoice_payload(payload, expected_sats)
            return payload
        raise SystemExit("no DM")
    from pynostr.filters import Filters, FiltersList
    from pynostr.relay_manager import RelayManager

    my_hex = sk.public_key.hex()
    mgr = RelayManager(timeout=min(8.0, max(2.0, wait_s)))
    for url in _relays():
        mgr.add_relay(url, timeout=3, close_on_eose=False)
    filt = Filters(kinds=[1059], pubkey_refs=[my_hex], limit=50)
    mgr.add_subscription_on_all_relays("a2a", FiltersList([filt]))
    seen: set[str] = set()
    try:
        while time.time() < deadline:
            mgr.run_sync()
            while mgr.message_pool.has_events():
                ev = mgr.message_pool.get_event().event
                eid = getattr(ev, "id", None) or ""
                if eid in seen:
                    continue
                seen.add(eid)
                wrap = {
                    "id": ev.id,
                    "pubkey": ev.pubkey,
                    "created_at": ev.created_at,
                    "kind": ev.kind,
                    "tags": ev.tags,
                    "content": ev.content,
                    "sig": ev.sig,
                }
                try:
                    payload, rumor = unwrap_payload(sk, wrap)
                except Exception:
                    continue
                if str(rumor.get("pubkey") or "") != from_hex:
                    continue
                try:
                    check_invoice_payload(payload, expected_sats)
                except ValueError:
                    continue
                return payload
            time.sleep(0.5)
    finally:
        mgr.close_all_relay_connections()
    raise SystemExit("no DM")


def cmd_pay_dm(args: argparse.Namespace, client: Any | None = None) -> int:
    sats = int(args.sats)
    wait_s = float(args.wait)
    if args.offline:
        inbox = getattr(args, "offline_inbox", None)
        if not inbox:
            raise SystemExit("no DM")
    from_hex = npub_to_hex(args.from_npub)
    if args.offline:
        sk = getattr(args, "offline_sk", None)
        payload = _poll_dm(sk, from_hex, sats, wait_s, inbox=inbox)
        check_invoice_payload(payload, sats)
        print("OFFLINE pay-dm would pay (no LND, no relay)")
        return 0
    _require_latches(pay=True)
    sk = _load_nostr(args.nostr_name)
    payload = _poll_dm(sk, from_hex, sats, wait_s)
    c = client or create_client()
    decoded = None
    try:
        decoded = c.lnd.decode_pay_req(payload["bolt11"])
    except Exception:
        decoded = None
    bolt11 = check_invoice_payload(payload, sats, decoded=decoded)
    args.bolt11 = bolt11
    return cmd_pay(args, client=c)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Two LND nodes: payee invoice, payer pays. Not swarm."
    )
    p.add_argument("--offline", action="store_true", help="No LND / no relays (tests)")
    sub = p.add_subparsers(dest="cmd", required=True)
    inv = sub.add_parser("invoice", help="Create invoice on this node's LND")
    inv.add_argument("--sats", type=int, default=DEFAULT_SATS)
    inv.add_argument("--memo", default="a2a-ln-pay")
    pay = sub.add_parser("pay", help="Pay a BOLT11 with this node's LND")
    pay.add_argument("--bolt11", required=True)
    idm = sub.add_parser(
        "invoice-dm", help="Create invoice and send encrypted Nostr DM"
    )
    idm.add_argument("--to-npub", required=True)
    idm.add_argument("--sats", type=int, default=DEFAULT_SATS)
    idm.add_argument("--memo", default="a2a-ln-pay")
    idm.add_argument("--nostr-name", default="a2a_payee")
    pdm = sub.add_parser("pay-dm", help="Receive encrypted DM and pay once")
    pdm.add_argument("--from-npub", required=True)
    pdm.add_argument("--sats", type=int, default=DEFAULT_SATS)
    pdm.add_argument("--wait", type=float, default=DEFAULT_WAIT)
    pdm.add_argument("--nostr-name", default="a2a_payer")
    args = p.parse_args(argv)
    if args.cmd == "invoice":
        return cmd_invoice(args)
    if args.cmd == "pay":
        return cmd_pay(args)
    if args.cmd == "invoice-dm":
        return cmd_invoice_dm(args)
    return cmd_pay_dm(args)


if __name__ == "__main__":
    raise SystemExit(main())
