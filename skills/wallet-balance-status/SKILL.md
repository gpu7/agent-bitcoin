---
name: wallet balance status
description: Reads on-chain and channel balances plus node status from an unlocked LND node.
summary: Report confirmed, unconfirmed, local, remote, and pending balances with getinfo.
version: 1.0.0
tags: lightning, wallet, balances
keywords: walletbalance, channelbalance, getinfo, agent-bitcoin
use_cases: Report wallet and channel balances before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Wallet balance and status

Read wallet and node state with the agent-bitcoin SDK. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read balances and node status only. Do not move funds and do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
wallet = client.get_balance()
channels = client.get_channel_balance()
```

Report `confirmed_balance` and `unconfirmed_balance`. Report `local_balance` and `remote_balance`. Report `alias`, `identity_pubkey`, `block_height`, `synced_to_chain`, `synced_to_graph`, `num_peers`, and `num_active_channels`.

If `get_info`, `get_balance`, or `get_channel_balance` fails with `wallet locked`, stop and say the wallet is locked.

`get_channel_balance()` does not include pending amounts. Read `pending_open_local_balance`, `pending_open_remote_balance`, `unsettled_local_balance`, and `unsettled_remote_balance` from `channelbalance`.

## lncli

When the SDK is not available, use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest walletbalance
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest channelbalance
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo
```

Read the same fields from that JSON.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
