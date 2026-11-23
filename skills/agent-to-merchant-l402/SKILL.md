---
name: agent to merchant l402 payment
description: Pays an L402-gated HTTP endpoint with the agent-bitcoin SDK and returns the resource.
summary: Pay an Aperture-style 402 challenge and fetch the resource.
version: 1.0.0
tags: lightning, l402, payments
keywords: l402, aperture, agent-bitcoin
use_cases: Pay a merchant endpoint that returns HTTP 402.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-l402-merchant-deployment-test.md
---

# Agent to merchant L402 payment

Pay one L402-gated HTTP URL and return the resource. Use the agent-bitcoin SDK. Do not add another payment path.

## Requirements

- Python 3.10+
- `pip install agent-bitcoin` with no version pin
- An unlocked LND node
- Regtest is the default network
- Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet spend
- Set `AGENT_BITCOIN_ALLOW_AUTOPAY=1` only when the user has asked for autopay

Do not set either variable on your own. Do not sign in to Agensi from this skill.

## Pay

```python
from agent_bitcoin import L402Client, create_client

response = L402Client(create_client()).fetch(url)
```

`url` is the merchant endpoint. Report `response.status_code` and `response.paid`.

## What to keep private

Do not print wallet secrets, macaroons, preimages, or BOLT11 invoices. Do not print the challenge object.
