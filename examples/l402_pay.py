#!/usr/bin/env python3
"""Pay an Aperture L402 endpoint with the local LND node (Mac payer).

Example (regtest, Mac → AWS):

    LND_NETWORK=regtest LND_CONTAINER=agent-bitcoin-lnd \\
      uv run python examples/l402_pay.py \\
      --url http://<AWS_EIP>:8081/paid/hello

Signet:

    LND_NETWORK=signet LND_CONTAINER=agent-bitcoin-lnd-signet \\
      uv run python examples/l402_pay.py \\
      --url http://<AWS_EIP>:8081/paid/hello

Mainnet (real sats; latches required):

    AGENT_BITCOIN_ALLOW_MAINNET=1 AGENT_BITCOIN_ALLOW_AUTOPAY=1 \\
    LND_NETWORK=mainnet LND_CONTAINER=agent-bitcoin-lnd-mainnet \\
      uv run python examples/l402_pay.py \\
      --url http://<AWS_EIP>:8081/paid/hello

Paid PDF (same 1,000 sat price):

    ... l402_pay.py --url http://<AWS_EIP>:8081/paid/report.pdf --out report.pdf
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
    parser.add_argument(
        "--out",
        default=os.getenv("L402_OUT", ""),
        help="Write body to this file (default: stdout; PDFs use report.pdf if unset)",
    )
    args = parser.parse_args()

    payer = create_client()
    client = L402Client(payer, expected_price_sats=args.price)
    print(f"GET {args.url}", flush=True)
    resp = client.fetch(args.url)
    print(f"status={resp.status_code} paid={resp.paid}", flush=True)
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    out_path = args.out
    if not out_path and ctype == "application/pdf":
        out_path = "report.pdf"
    if out_path:
        with open(out_path, "wb") as fh:
            fh.write(resp.body)
        print(f"wrote {len(resp.body)} bytes to {out_path} ({ctype or 'unknown'})")
    elif ctype == "application/json" or resp.body[:1] == b"{":
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text())
    else:
        print(resp.text())
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
