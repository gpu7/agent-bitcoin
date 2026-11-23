---
name: peer status connectivity
description: Lists connected Lightning peers and the peer count from an unlocked LND node.
summary: Read peer address, traffic, and ping time, plus num_peers.
version: 1.0.0
tags: lightning, peers, connectivity
keywords: listpeers, getinfo, num_peers, agent-bitcoin
use_cases: Report Lightning peer connectivity before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Peer status and connectivity

Read Lightning peer state with the agent-bitcoin SDK and lncli. An unlocked LND node is required. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

Read peer state only. Do not change peer connections and do not change channel state.

Do not sign in to Agensi from this skill.

## Check

```python
from agent_bitcoin import create_client

client = create_client()
info = client.lnd.get_info()
```

Report `num_peers` when `info` contains it. If `get_info` or `listpeers` fails with `wallet locked`, stop and say the wallet is locked.

## lncli

The SDK has no peer-list call. Use the same container and flags:

```bash
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo
docker exec -i agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers
```

`num_peers` is on the `getinfo` JSON. For each item in `peers`, report `pub_key`, `address`, `bytes_sent`, `bytes_recv`, `sat_sent`, `sat_recv`, `inbound`, and `ping_time`. LND reports `ping_time` in nanoseconds.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
