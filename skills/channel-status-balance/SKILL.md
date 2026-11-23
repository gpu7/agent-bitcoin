---
name: channel status balance
description: Lists open Lightning channels and reports balances from an unlocked LND node.
summary: Read channel activity, capacity, and local and remote balances.
version: 1.0.0
tags: lightning, channels, balances
keywords: listchannels, getinfo, channel balance, agent-bitcoin
use_cases: Report Lightning channel status and balances before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Channel status and balance

Read Lightning channel state with the agent-bitcoin SDK. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read channel state only. Do not move funds and do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
payload = client.lnd.list_channels()
```

`payload["channels"]` is the channel list. For each channel, report `active`, `local_balance`, `remote_balance`, `capacity`, `remote_pubkey`, and `chan_id`. Sum `local_balance` and `remote_balance` across that list. When `info` contains `num_peers`, report it.

If `get_info` or `list_channels` fails with `wallet locked`, stop and say the wallet is locked.

## lncli

When the SDK is not available, use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listchannels
```

Read the same fields from the `listchannels` JSON. `num_peers` is on the `getinfo` JSON.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
