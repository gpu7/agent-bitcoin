#!/usr/bin/env python3
"""Two LND nodes: AWS payee invoices, Mac/Ubuntu payer pays (optional LLM gate).

Not the merchant demo (one wallet → Aperture). Reuses a2a_ln_pay.py for
invoice-dm / pay-dm and merchant ask_gate for grok|ollama.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

_EX = Path(__file__).resolve().parent
if str(_EX) not in sys.path:
    sys.path.insert(0, str(_EX))

import a2a_ln_pay as a2a  # noqa: E402
from agent_bitcoin.nostr.resolve import parse_force_vote  # noqa: E402


def _merchant_ask_gate():
    path = _EX / "agent-to-merchant-pay.py"
    spec = importlib.util.spec_from_file_location("merchant_pay_gate", path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load agent-to-merchant-pay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ask_gate


def _gate(job: str, backend: str) -> tuple[str, str]:
    try:
        forced = parse_force_vote(os.environ.get("A2A_LLM_FORCE_VOTE"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if forced:
        return forced, "forced_test"
    return _merchant_ask_gate()(job, backend)


def _parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="A2A Lightning: two nodes, 100-sat invoice via encrypted DM. Not merchant swarm."
    )
    p.add_argument("--role", choices=("payee", "payer"), required=True)
    p.add_argument("--sats", type=int, default=100)
    p.add_argument("--no-llm", action="store_true")
    p.add_argument("--model", choices=("grok", "ollama"), default="")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--wait", type=float, default=60)
    p.add_argument("--to-npub", default="")
    p.add_argument("--from-npub", default="")
    p.add_argument("--nostr-name", default="")
    p.add_argument("--memo", default="a2a-ln-pay")
    args = p.parse_args(argv)
    if args.no_llm and args.model:
        raise SystemExit("--no-llm cannot be combined with --model")
    if args.role == "payee" and not args.offline and not args.to_npub:
        raise SystemExit("payee needs --to-npub (payer npub)")
    if args.role == "payer" and not args.offline and not args.from_npub:
        raise SystemExit("payer needs --from-npub (payee npub)")
    if not args.nostr_name:
        args.nostr_name = "a2a_payee" if args.role == "payee" else "a2a_payer"
    return args


def run_payee(args: argparse.Namespace) -> int:
    ns = SimpleNamespace(
        offline=args.offline,
        to_npub=args.to_npub or "npub1unused",
        sats=int(args.sats),
        memo=args.memo,
        nostr_name=args.nostr_name,
    )
    return a2a.cmd_invoice_dm(ns)


def run_payer(args: argparse.Namespace, client=None) -> int:
    job = (
        f"Should this agent pay {int(args.sats)} sats A2A Lightning "
        f"(two LND nodes, not Aperture)? Reply YES or NO."
    )
    ns = SimpleNamespace(
        offline=args.offline,
        from_npub=args.from_npub or "npub1unused",
        sats=int(args.sats),
        wait=float(args.wait),
        nostr_name=args.nostr_name,
        offline_inbox=getattr(args, "offline_inbox", None),
        offline_sk=getattr(args, "offline_sk", None),
        bolt11="",
    )
    if args.offline:
        inbox = getattr(args, "offline_inbox", None)
        if not inbox:
            raise SystemExit("no DM")
        from_hex = a2a.npub_to_hex(args.from_npub)
        payload = a2a._poll_dm(
            args.offline_sk, from_hex, int(args.sats), float(args.wait), inbox=inbox
        )
        a2a.check_invoice_payload(payload, int(args.sats))
        if args.model:
            vote, reason = _gate(job, args.model)
            print(f"[payer] vote={vote} reason={reason}")
            if vote != "YES":
                print("[payer] skip pay")
                return 0
        print("OFFLINE pay-dm would pay (no LND, no relay)")
        return 0
    # live: receive then optional gate then pay
    from_hex = a2a.npub_to_hex(args.from_npub)
    a2a._require_latches(pay=True)
    sk = a2a._load_nostr(args.nostr_name)
    payload = a2a._poll_dm(sk, from_hex, int(args.sats), float(args.wait))
    decoded = None
    c = client or a2a.create_client()
    try:
        decoded = c.lnd.decode_pay_req(payload["bolt11"])
    except Exception:
        decoded = None
    bolt11 = a2a.check_invoice_payload(payload, int(args.sats), decoded=decoded)
    if args.model:
        vote, reason = _gate(job, args.model)
        print(f"[payer] vote={vote} reason={reason}")
        if vote != "YES":
            print("[payer] skip pay")
            return 0
    ns.bolt11 = bolt11
    ns.offline = False
    return a2a.cmd_pay(ns, client=c)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    if args.role == "payee":
        return run_payee(args)
    return run_payer(args)


if __name__ == "__main__":
    raise SystemExit(main())
