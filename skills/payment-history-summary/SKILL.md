---
name: payment history summary
description: Summarizes recent sent and received Lightning payments from an unlocked LND node.
summary: Report counts, totals, and a short sample without preimages.
version: 1.0.0
tags: lightning, payments, history
keywords: listpayments, listinvoices, getinfo, agent-bitcoin
use_cases: Read recent Lightning payment history before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Payment history summary

Read Lightning payment history with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read payment history only. Do not change payment state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
```

If `get_info` or a later call fails with `wallet locked`, stop and say the wallet is locked.

The SDK has no history call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpayments --max_payments 10
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listinvoices --reversed --max_invoices 10
```

`listpayments` is sent. Report the count and the sum of `value_sat`. For at most five rows, report `value_sat`, `status`, and either `creation_time_ns` or the first eight characters of `payment_hash`.

`listinvoices` is received. Report the count and the sum of `amt_paid_sat`. For at most five rows, report `value`, `settled`, and either `creation_date` or the first eight characters of `r_hash`.

Do not print `payment_preimage`, `r_preimage`, a full hash, or a BOLT11 string.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
