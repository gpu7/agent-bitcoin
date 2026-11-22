#!/usr/bin/env python3
"""Buyer check for the public Agensi listing.

Run this with the Python from a fresh virtualenv whose only install was
``pip install agent-bitcoin`` (or ``pip install .`` of that same package).

Phases
------
install
    Import the package. Then call ``agent_bitcoin.pay_invoice("")``, the
    function named on the listing, with no invoice. The phase succeeds when
    that call raises ``ValueError`` for a missing payment request. An
    ``AttributeError`` fails the phase.
pay
    Create an invoice, pay it, and require a settled receipt. The operator
    must already have the unlocked LND node the listing requires. This phase
    does not start a node and does not set mainnet flags.
"""

from __future__ import annotations

import argparse
import sys
import traceback


LISTING = "https://www.agensi.io/skills/agent-to-agent-lightning-payment"
# The worked example on the listing pays 500 sats.
EXAMPLE_AMOUNT_SATS = 500


def phase_install() -> int:
    try:
        import agent_bitcoin
    except Exception:
        print("import agent_bitcoin failed", file=sys.stderr)
        traceback.print_exc()
        return 1

    version = getattr(agent_bitcoin, "__version__", "unknown")
    print(f"imported agent-bitcoin {version}", flush=True)
    print("--- listing call: agent_bitcoin.pay_invoice('') ---", flush=True)
    try:
        agent_bitcoin.pay_invoice("")
    except AttributeError:
        traceback.print_exc()
        return 1
    except ValueError as exc:
        print(f"{type(exc).__name__}: {exc}", flush=True)
        if "Payment request" in str(exc):
            return 0
        print("unexpected ValueError", file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        return 1
    print("pay_invoice('') returned without an error", file=sys.stderr)
    return 1


def phase_pay() -> int:
    try:
        import agent_bitcoin
    except Exception:
        print("import agent_bitcoin failed", file=sys.stderr)
        traceback.print_exc()
        return 1

    try:
        client = agent_bitcoin.create_client()
        invoice = client.create_invoice(
            memo="agensi public buyer",
            amount_sats=EXAMPLE_AMOUNT_SATS,
        )
        result = agent_bitcoin.pay_invoice(invoice.payment_request)
    except Exception:
        traceback.print_exc()
        return 1

    status = getattr(result, "status", "")
    success = bool(getattr(result, "success", False))
    amount = getattr(result, "amount", None)
    has_hash = bool(getattr(result, "payment_hash", None))
    print(
        f"status={status} success={success} "
        f"amount_sats={amount} payment_hash={'present' if has_hash else 'absent'}"
    )
    if success and has_hash and str(status).upper() == "SUCCEEDED":
        return 0
    print("payment did not settle", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Public buyer check for {LISTING}")
    parser.add_argument("--phase", choices=("install", "pay"), required=True)
    args = parser.parse_args(argv)
    if args.phase == "install":
        return phase_install()
    return phase_pay()


if __name__ == "__main__":
    sys.exit(main())
