#!/usr/bin/env python3
"""Pay an Aperture L402 endpoint with the local LND node (Mac payer).

Example (regtest, Mac → AWS):

    LND_NETWORK=regtest LND_CONTAINER=agent-bitcoin-lnd \\
      uv run python examples/l402_pay.py \\
      --url http://<AWS_EIP>:8081/paid/hello
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from agent_bitcoin import L402Client, create_client
from agent_bitcoin.constants import DEFAULT_L402_PRICE_SATS


def main() -> int:
    parser = argparse.ArgumentParser(description="Pay an L402 HTTP resource")
    parser.add_argument(
        "--url",
        default=os.getenv("L402_URL", "http://127.0.0.1:8081/paid/hello"),
        help="Paid URL (default: %(default)s or L402_URL)",
    )
    parser.add_argument(
        "--price",
        type=int,
        default=int(os.getenv("L402_PRICE_SATS", str(DEFAULT_L402_PRICE_SATS))),
        help="Expected invoice amount in sats (default: %(default)s)",
    )
    args = parser.parse_args()

    payer = create_client()
    client = L402Client(payer, expected_price_sats=args.price)
    print(f"GET {args.url}", flush=True)
    resp = client.fetch(args.url)
    print(f"status={resp.status_code} paid={resp.paid}", flush=True)
    try:
        print(json.dumps(resp.json(), indent=2))
    except Exception:
        print(resp.text())
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
