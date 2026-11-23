---
name: payment status tracking
description: Reads Lightning payment status and recent payments from an unlocked LND node.
summary: Report in-flight, succeeded, or failed status, amount, fee, and a settled preimage.
version: 1.0.0
tags: lightning, payments, status
keywords: trackpayment, lookupinvoice, listpayments, agent-bitcoin
use_cases: Check one Lightning payment and list recent payments.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Payment status and tracking

Read Lightning payment state with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read payment state only. Do not move funds and do not cancel a payment.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
decoded = client.lnd.decode_pay_req(payment_request)
```

`decoded["payment_hash"]` is the hash. When the caller already has a 64-character hex hash, skip `decode_pay_req`. If `get_info` or a later call fails with `wallet locked`, stop and say the wallet is locked.

## lncli

The SDK has no status or history call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest trackpayment --payment_hash <hash>
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest lookupinvoice --rhash <hash>
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpayments --max_payments 10
```

Map `IN_FLIGHT`, `OPEN`, and `ACCEPTED` to in-flight. Map `SUCCEEDED` and `SETTLED` to succeeded. Map `FAILED` and `CANCELED` to failed.

For the one payment being checked, report that status, the amount, the fee, the preimage when the status is succeeded, and `failure_reason` when it is present. The `listpayments` rows are a short summary of status, amount, and fee. Do not print preimages in that list.

## What to keep private

Do not print wallet secrets or macaroons.
