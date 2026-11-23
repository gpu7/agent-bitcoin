#!/usr/bin/env python3
"""Buyer check for the Agensi L402 merchant skill.

Run this with the Python from a fresh virtualenv whose only install was
``pip install agent-bitcoin``. The install phase checks ``L402Client.fetch``
and the mainnet and autopay latches. It does not call ``fetch`` and does not pay.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback


def phase_install() -> int:
    try:
        import agent_bitcoin
        from agent_bitcoin.exceptions import ConfigurationError
    except Exception:
        print("import agent_bitcoin failed", file=sys.stderr)
        traceback.print_exc()
        return 1

    fetch = getattr(getattr(agent_bitcoin, "L402Client", None), "fetch", None)
    if not callable(fetch):
        print("L402Client.fetch missing", file=sys.stderr)
        return 1

    version = getattr(agent_bitcoin, "__version__", "unknown")
    print(f"imported agent-bitcoin {version}", flush=True)
    print("L402Client.fetch present", flush=True)

    os.environ["LND_NETWORK"] = "mainnet"
    os.environ["LND_TRANSPORT"] = "docker"
    os.environ.pop("AGENT_BITCOIN_ALLOW_MAINNET", None)
    os.environ.pop("AGENT_BITCOIN_ALLOW_AUTOPAY", None)
    try:
        agent_bitcoin.L402Client(agent_bitcoin.create_client())
    except ConfigurationError as exc:
        print(f"{type(exc).__name__}: {exc}", flush=True)
        if "ALLOW_MAINNET" not in str(exc):
            print("unexpected configuration error", file=sys.stderr)
            return 1
    except Exception:
        traceback.print_exc()
        return 1
    else:
        print("mainnet client was created without ALLOW_MAINNET", file=sys.stderr)
        return 1

    os.environ["AGENT_BITCOIN_ALLOW_MAINNET"] = "1"
    os.environ.pop("AGENT_BITCOIN_ALLOW_AUTOPAY", None)
    try:
        agent_bitcoin.pay_invoice("lnbc1dryrun")
    except RuntimeError as exc:
        print(f"{type(exc).__name__}: {exc}", flush=True)
        if "ALLOW_AUTOPAY" not in str(exc):
            print("unexpected RuntimeError", file=sys.stderr)
            return 1
    except Exception:
        traceback.print_exc()
        return 1
    else:
        print("pay_invoice returned without the autopay latch", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L402 merchant buyer check")
    parser.add_argument("--phase", choices=("install",), required=True)
    parser.parse_args(argv)
    return phase_install()


if __name__ == "__main__":
    sys.exit(main())
