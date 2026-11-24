---
name: fee estimation routing
description: Estimates on-chain and Lightning routing fees from an unlocked LND node.
summary: Report fee rates and route fee breakdowns without sending a payment.
version: 1.0.0
tags: lightning, fees, routing
keywords: estimatefee, queryroutes, estimateroutefee, agent-bitcoin
use_cases: Estimate a fee before any payment is attempted.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Fee estimation and routing

Read fee estimates with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read fee estimates only. Do not move funds and do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
decoded = client.lnd.decode_pay_req(payment_request)
```

`decoded` supplies the destination and amount for a route query. When the caller already has a destination pubkey and an amount, skip `decode_pay_req`. If `get_info` or a later call fails with `wallet locked`, stop and say the wallet is locked.

The SDK has no fee-estimate call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest estimatefee --addr=<address> --amount=<sats>
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest queryroutes --dest=<pubkey> --amt=<sats>
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest estimateroutefee --dest=<pubkey> --amt=<sats>
```

From `estimatefee`, report `fee_sat`, `feerate_sat_per_byte`, and `sat_per_vbyte`. From the first `queryroutes` route, report `total_fees`, `total_fees_msat`, and each hop `fee_msat`. From `estimateroutefee`, report `routing_fee_msat`. These commands only estimate. They do not broadcast.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
