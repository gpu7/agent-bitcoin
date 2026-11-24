---
name: invoice list status
description: Lists recent Lightning invoices and their settled state from an unlocked LND node.
summary: Report payment hash, amount, memo, expiry, and amount paid for the last invoices.
version: 1.0.0
tags: lightning, invoices, status
keywords: listinvoices, getinfo, agent-bitcoin
use_cases: Read recent Lightning invoices before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Invoice list and status

Read Lightning invoices with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read invoices only. Do not change invoice state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
```

If `get_info` or `listinvoices` fails with `wallet locked`, stop and say the wallet is locked.

The SDK has no invoice-list call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listinvoices --reversed --max_invoices 10
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listinvoices --pending_only --reversed --max_invoices 10
```

The first command is the last 10 invoices, newest first. The second is the same limit, unsettled only.

For each item in `invoices`, report `r_hash` as the payment hash, `value` as the requested amount, `memo`, `settled`, `creation_date`, `expiry`, and `amt_paid_sat` when `settled` is true.

## What to keep private

Do not print wallet secrets, macaroons, preimages, or BOLT11 strings.
