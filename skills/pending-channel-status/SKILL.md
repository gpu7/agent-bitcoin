---
name: pending channel status
description: Lists pending Lightning channels and their expiry from an unlocked LND node.
summary: Report pending opens and closes with capacity, balances, and initiator.
version: 1.0.0
tags: lightning, channels, pending
keywords: pendingchannels, getinfo, agent-bitcoin
use_cases: Report channels that are opening or closing before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Pending channel status

Read pending Lightning channel state with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read pending channel state only. Do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
```

If `get_info` or `pendingchannels` fails with `wallet locked`, stop and say the wallet is locked.

The SDK lists settled channels only. Pending rows use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest pendingchannels
```

Map each list to a type:

- `pending_open_channels` is pending open. Expiry is `funding_expiry_blocks`.
- `pending_closing_channels` is pending close. There is no expiry block. Report `closing_txid` when it is present.
- `waiting_close_channels` is waiting close. There is no expiry block.
- `pending_force_closing_channels` is force close. Timeout is `blocks_til_maturity` and `maturity_height`.

For each row, read `capacity`, `local_balance`, `remote_balance`, and `initiator` from the nested `channel` object. The summary is the count of `pending_open_channels` and the count of the other three lists added together.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
