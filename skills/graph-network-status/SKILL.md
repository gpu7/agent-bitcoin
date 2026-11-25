---
name: graph network status
description: Summarizes the Lightning graph and peer count from an unlocked LND node.
summary: Report node count, channel count, num_peers, and a few node aliases.
version: 1.0.0
tags: lightning, graph, network
keywords: describegraph, getnetworkinfo, getinfo, agent-bitcoin
use_cases: Read Lightning graph size and a short node sample before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Graph and network status

Read Lightning graph state with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read graph state only. Do not change peer connections and do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
```

Report `num_peers` when `info` contains it. If `get_info` or a later call fails with `wallet locked`, stop and say the wallet is locked.

The SDK has no graph call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getnetworkinfo
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest describegraph
```

From `getnetworkinfo`, report `num_nodes` and `num_channels`. From `describegraph`, report the length of `nodes` and the length of `edges`, plus at most five `alias` values. Do not print the `edges` list or a full `pub_key`.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
