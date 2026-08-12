#!/usr/bin/env python3
"""N5 product path: decide PAY/REJECT → settle only via NWC (no LND in agent).

Default: rule-based decision + mock NWC service (offline CI-friendly).

  export AGENT_BITCOIN_NWC_ENABLE=1
  uv run --python 3.12 python examples/nwc_decision_pay.py --mock

Optional LLM decision (requires xAI or Ollama setup):

  export XAI_API_KEY=...
  uv run --python 3.12 python examples/nwc_decision_pay.py --mock --llm grok

Live LND (regtest): omit --mock; ensure docker LND unlocked.
PaymentDecisionAgent never executes pays — only NWC does after PAY.
"""

from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace


def _fake_lnd(amount: int):
    class FakeLND:
        def get_info(self):
            return {
                "alias": "n5-mock",
                "identity_pubkey": "aa" * 32,
                "chains": [{"network": "regtest"}],
                "block_height": 1,
                "block_hash": "bb" * 32,
            }

        def get_channel_balance(self):
            return SimpleNamespace(local_balance=100_000, remote_balance=50_000)

        def get_balance(self):
            return SimpleNamespace(confirmed_balance="0")

        def create_invoice(self, memo, amount_sats, expiry_seconds=3600):
            return SimpleNamespace(
                payment_request=f"lnbcrt_n5_{amount_sats}",
                payment_hash="cc" * 32,
                r_hash="cc" * 32,
            )

        def decode_pay_req(self, pr):
            return {"num_satoshis": str(amount)}

        def pay_invoice(self, pr, fee_limit_sats=200):
            return SimpleNamespace(
                success=True, payment_hash="ee" * 32, status="SUCCEEDED"
            )

    return FakeLND()


def main() -> int:
    p = argparse.ArgumentParser(description="Decision → NWC pay product path (N5)")
    p.add_argument("--amount", type=int, default=2000, help="sats (default 2000)")
    p.add_argument("--mock", action="store_true", help="FakeLND, no Docker")
    p.add_argument(
        "--llm",
        choices=["", "grok", "ollama"],
        default="",
        help="Optional PaymentDecisionAgent backend (default: rule-based)",
    )
    p.add_argument(
        "--memo",
        default="nwc-decision-pay",
        help="Invoice memo / decision context",
    )
    args = p.parse_args()

    try:
        from pynostr.key import PrivateKey
    except ImportError:
        print(
            "Need nostr extra: uv sync --python 3.12 --extra nostr --group dev",
            file=sys.stderr,
        )
        return 2

    os.environ.setdefault("AGENT_BITCOIN_NWC_ENABLE", "1")
    os.environ.setdefault("LND_TRANSPORT", "docker")

    from agent_bitcoin.nwc.bus import InMemoryNWCBus
    from agent_bitcoin.nwc.client import NWCClient
    from agent_bitcoin.nwc.flow import (
        decision_is_pay,
        nwc_pay_if_approved,
        rule_based_decision,
    )
    from agent_bitcoin.nwc.policy import NWCBudgetPolicy
    from agent_bitcoin.nwc.service import NWCService

    bus = InMemoryNWCBus()
    if args.mock:
        lnd = _fake_lnd(args.amount)
        print("[n5] backend=FakeLND (--mock)")
    else:
        from agent_bitcoin.lightning import LNDClient

        lnd = LNDClient()
        print(f"[n5] backend=LND network={os.getenv('LND_NETWORK', 'regtest')}")

    svc = NWCService(
        wallet_sk=PrivateKey(),
        lnd=lnd,
        bus=bus,
        budget=NWCBudgetPolicy.from_env(),
        require_enable=True,
    )
    svc.attach()
    uri = svc.issue_connection()
    # Agent holds only URI — never LND macaroon
    agent_client = NWCClient(uri, relay=bus, default_timeout=30.0)

    # --- Decision (recommend only) ---
    if args.llm == "grok":
        from agent_bitcoin.agents.payment_decision import (
            create_grok_payment_decision_agent,
        )

        agent = create_grok_payment_decision_agent()
        decision = agent.decide_payment(
            {
                "amount_sats": args.amount,
                "memo": args.memo,
                "payment_request": "(pending invoice)",
            },
            context=args.memo,
        )
        print(f"[n5] PaymentDecisionAgent(grok) => {decision}")
    elif args.llm == "ollama":
        from agent_bitcoin import create_payment_decision_agent
        from langchain_ollama import ChatOllama

        llm = ChatOllama(model=os.getenv("OLLAMA_MODEL", "llama3.2"), temperature=0.1)
        agent = create_payment_decision_agent(llm=llm)
        # older API shape in payment_decision_agent example uses decide()
        if hasattr(agent, "decide_payment"):
            decision = agent.decide_payment(
                {
                    "amount_sats": args.amount,
                    "memo": args.memo,
                    "payment_request": "(pending invoice)",
                },
                context=args.memo,
            )
        else:
            decision = agent.decide(
                from_agent="payer-agent",
                to_agent="payee-agent",
                amount_sats=args.amount,
                reason=args.memo,
            )
        print(f"[n5] PaymentDecisionAgent(ollama) => {decision}")
    else:
        decision = rule_based_decision(args.amount, context=args.memo)
        print(f"[n5] rule_based_decision => {decision}")

    if not decision_is_pay(decision):
        print("[n5] STOP: decision is not PAY — no NWC pay executed")
        print("\nRESULT: PASS — reject path (decision gate held)")
        return 0

    # --- Settlement only after PAY ---
    inv = agent_client.make_invoice(args.amount, description=args.memo)
    print(f"[n5] invoice created via NWC: {str(inv.get('invoice', ''))[:40]}…")

    paid = nwc_pay_if_approved(
        agent_client,
        decision,
        inv["invoice"],
        amount_sats=args.amount,
    )
    if paid is None:
        print("[n5] unexpected: PAY but pay_if_approved returned None")
        return 1
    print(f"[n5] NWC pay result: {paid}")
    print("\nRESULT: PASS — decision PAY → NWC settle (agent had no LND macaroon)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
