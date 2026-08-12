#!/usr/bin/env python3
"""Print Dual-host mainnet NWC pay runbook (2k). Does not send funds."""

from __future__ import annotations

TEXT = """
M3 Dual-host mainnet pay (optional, 2000 sats) — operator steps

NWC invoice on AWS is already proven (N6). Paying it from Mac uses the Dual
private channel (M2). This is NOT always-on autopay.

--- AWS (create invoice via NWC) ---
  export LND_NETWORK=mainnet
  export AGENT_BITCOIN_ALLOW_MAINNET=1
  export AGENT_BITCOIN_NWC_ENABLE=1
  export AGENT_BITCOIN_NWC_ALLOW_MAINNET=1
  export LND_TRANSPORT=docker
  export LND_CONTAINER=agent-payment-decision-lnd-mainnet

  uv run --python 3.12 python examples/nwc_mainnet_smoke.py \\
    --yes-mainnet --amount 2000
  # copy the printed bolt11 (or addinvoice from lncli)

  unset AGENT_BITCOIN_NWC_ALLOW_MAINNET AGENT_BITCOIN_NWC_ENABLE \\
        AGENT_BITCOIN_ALLOW_MAINNET

--- Mac (pay AWS invoice over Dual channel) ---
  docker exec agent-bitcoin-lnd-mainnet \\
    lncli --lnddir=/home/lnd/.lnd --network=mainnet \\
    sendpayment --pay_req='lnbc…' --fee_limit 50 --json --force

Do not raise amount without a new go. Do not leave NWC latches set.
"""


def main() -> int:
    print(TEXT.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
