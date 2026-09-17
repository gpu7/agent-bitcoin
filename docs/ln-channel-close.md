# Lightning channel close → Bitcoin on-chain

Operator note. **Do not close the lab channel unless you intend to.** Agents and the SDK never call `closechannel`.

Opening a channel is **not** Bitcoin settlement. Aperture L402 pays (typically **100 sats**) stay **off-chain** as Lightning HTLCs / balance updates until the channel is closed. Then the remaining balances become on-chain UTXOs in LND’s Bitcoin wallet (`walletbalance`).

Private channels are fine. Wait for confirmations on open and on close.

## Cooperative vs force-close

| | Cooperative | Force-close |
|---|-------------|-------------|
| When | Both nodes online and agree | Peer missing or uncooperative |
| Chain | One closing tx, then wait for confirms | CSV delay + extra txs; more fees |
| Prefer | **Yes**, when you mean to settle on-chain | Only if you must |

This lab’s Phase 8 dual-node close was **cooperative**. See [mainnet-pilot.md](./mainnet-pilot.md).

## Commands (mainnet containers)

Mac: `agent-bitcoin-lnd-mainnet`. AWS: `agent-payment-decision-lnd-mainnet`. Always `--lnddir=/home/lnd/.lnd --network=mainnet`.

List:

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listchannels
docker exec agent-payment-decision-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet listchannels
```

Cooperative close **only if you intend to** (take `channel_point` from `listchannels`, `txid:index`):

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet closechannel --chan_point <txid:index>
```

Pending, then on-chain balance after confirms:

```bash
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet pendingchannels
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd \
  --network=mainnet walletbalance
```

Same `lncli` flags on AWS with `agent-payment-decision-lnd-mainnet`. Wait until `pendingchannels` is empty and `confirmed_balance` includes the close. Do not paste preimages or seeds.

Wallets diagram: [architecture.md](./architecture.md#wallets-and-chain-backends).
