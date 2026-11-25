---
name: node connectivity summary
description: Summarizes peers, channel counts, and graph reach from an unlocked LND node.
summary: Report num_peers, active and inactive channels, and a short peer sample.
version: 1.0.0
tags: lightning, peers, connectivity
keywords: getinfo, listpeers, num_peers, agent-bitcoin
use_cases: Read node connectivity before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Node connectivity summary

Read node connectivity with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read node connectivity only. Do not change peer connections and do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
```

Report `num_peers`, `num_active_channels`, `num_inactive_channels`, and `synced_to_graph` when `info` contains them. `synced_to_graph` is the graph-reach indicator. If `get_info` or `listpeers` fails with `wallet locked`, stop and say the wallet is locked.

The SDK has no peer-list call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers
```

From `listpeers`, report at most five peers. For each, report `alias` when the row has it, otherwise `pub_key`. Do not print the rest of the peer list.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
