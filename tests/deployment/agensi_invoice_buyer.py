#!/usr/bin/env python3
"""Buyer check for the Agensi invoice decode skill.

Run this with the Python from a fresh virtualenv whose only install was
``pip install agent-bitcoin``. The install phase checks
``inspect_payment_hashes`` on an invalid invoice. It does not pay.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback


def phase_install() -> int:
    try:
        import agent_bitcoin
        from agent_bitcoin.bolt11_invoice import inspect_payment_hashes
    except Exception:
        print("import agent_bitcoin failed", file=sys.stderr)
        traceback.print_exc()
        return 1

    if not callable(inspect_payment_hashes):
        print("inspect_payment_hashes missing", file=sys.stderr)
        return 1

    version = getattr(agent_bitcoin, "__version__", "unknown")
    print(f"imported agent-bitcoin {version}", flush=True)
    print("inspect_payment_hashes present", flush=True)

    os.environ.pop("AGENT_BITCOIN_ALLOW_MAINNET", None)
    if os.environ.get("AGENT_BITCOIN_ALLOW_MAINNET"):
        print("mainnet latch is set", file=sys.stderr)
        return 1
    print("mainnet_latch=unset", flush=True)

    for sample in ("lnbc1notvalid", ""):
        if inspect_payment_hashes(sample) is not None:
            print("invalid invoice was accepted", file=sys.stderr)
            return 1
    print("bad_invoice", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Invoice decode buyer check")
    parser.add_argument("--phase", choices=("install",), required=True)
    parser.parse_args(argv)
    return phase_install()


if __name__ == "__main__":
    sys.exit(main())
