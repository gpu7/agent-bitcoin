# Signet operator guide (v1)

**Audience:** Operators moving from private **regtest** to public **signet**.
**Agents / SDK:** still do **not** open channels or run Loop. Payment agents stay invoice / pay / decide.

**Related:** [backend.md](./backend.md) (regtest ops) · [liquidity-automation.md](./liquidity-automation.md) · [SECURITY.md](../SECURITY.md)

---

## Why signet (after regtest)

| | Regtest | Signet |
|--|---------|--------|
| Coins | Infinite (mine) | Finite faucet coins |
| Sync | Local / instant-ish | Public chain (first sync can be long) |
| Peers | Your Mac + AWS only | Public LN peers (or your second node) |
| Loop Autoloop | Full local lab | **Deferred** (regtest tools first) |
| Risk | None | Still not real money; good pre-mainnet |

**v1 success:** SDK + backend create invoices and complete at least one Lightning payment on **signet** with an active channel.

---

## What this repo provides (Phase 1 tooling)

| Piece | Purpose |
|-------|---------|
| `docker-compose.signet.aws.yml` | Neutrino LND on AWS signet; volume `agent-bitcoin_lnd-signet-data` |
| `docker-compose.signet.mac.yml` | **bitcoind + LND** on Mac signet (dual-node peer) |
| `startup-signet-aws.sh` / `shutdown-signet-aws.sh` | AWS start/stop (keep volume) |
| `startup-signet-mac.sh` / `shutdown-signet-mac.sh` | Mac start/stop (keep volumes) |
| `LND_NETWORK=signet` | SDK / `LNDClient` |
| `LND_CONTAINER=...` | e.g. `agent-payment-decision-lnd-signet` |

**Does not** replace or delete regtest compose/scripts. Do **not** reuse regtest wallet volumes for signet.

### Neutrino vs bitcoind (chain backends)

LND needs a **Bitcoin chain backend**. Two options:

| | **Neutrino** (light client) | **bitcoind** (full node) |
|--|----------------------------|---------------------------|
| What it is | LND embeds [lightninglabs/neutrino](https://github.com/lightninglabs/neutrino): downloads headers + compact filters (BIP157) from other nodes | Bitcoin Core runs next to LND; LND talks RPC + ZMQ |
| Disk | Small (headers/filters) | Larger (full signet chain, multi‑GB) |
| Peers needed | Public nodes that serve **compact filters** (`peerblockfilters=1`) | Normal Bitcoin P2P (many signet peers) |
| Reliability | Fragile if public CF peers are sparse/bad (common on Docker Desktop Mac) | Predictable: you control the node |
| This repo | **AWS** signet (still Neutrino) | **Mac** signet (bitcoind after Neutrino failed) |

**bitcoind-signet is the alternative to Neutrino** for the Mac counterparty: same LND, same Lightning wallet role, different way of learning the Bitcoin tip. You cannot switch an existing wallet between Neutrino and bitcoind — wipe the LND volume once when migrating (see Mac section).

---

## Topology (v1 recommendation)

```text
AWS: agent-payment-decision-lnd-signet  (Neutrino, P2P :19735)
        |
   Lightning channel (signet)
        |
Mac: bitcoind-signet ──RPC/ZMQ──► agent-bitcoin-lnd-signet  (P2P :29735)
```

- **AWS host ports:** `19735` (P2P), `20009` (RPC) — avoid regtest `9735` / `10009`.
- **Mac host ports:** `29735` (LN P2P), `30009` (LND gRPC), `38332`/`38333` (bitcoind RPC/P2P lab).
- Prefer **Mac → AWS connect** (outbound from home network).
- AWS and Mac LND only need to agree on the **same signet tip** for channels; backends can differ.

---

## Step-by-step

### 1) Code on the instance

```bash
cd ~/agent-bitcoin
git pull origin main
chmod +x startup-signet-aws.sh shutdown-signet-aws.sh
```

### 2) Start signet LND

```bash
export AWS_IP=3.90.159.146   # your EIP — must be non-empty
./startup-signet-aws.sh "$AWS_IP"
# create or unlock wallet when prompted
```

### 3) Wait for chain sync

```bash
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_NETWORK=signet

docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo \
  | grep -E 'identity_pubkey|block_height|synced_to_chain'
```

Repeat until `synced_to_chain: true` (can take a long time on first Neutrino sync).

### 4) Fund wallet

```bash
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet newaddress p2wkh
# Use a Bitcoin signet faucet with that address; wait for confirmations
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet walletbalance
```

### 5) Backend / SDK

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export AGENT_BITCOIN_API_KEY=...   # from .env

# Start backend as usual (tmux / uvicorn) with those env vars in the process environment
curl -s http://127.0.0.1:8000/
# Create invoice via API or:
# LND_NETWORK=signet LND_CONTAINER=... uv run python -c "from agent_bitcoin import create_client; print(create_client().create_invoice('signet', 2000))"
```

### 6) Open a channel (operator)

```bash
# Connect to a signet peer (pubkey@host:port — use a current public signet LN peer list)
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet connect <pubkey>@<host>:9735

docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet openchannel \
  --node_key=<pubkey> --local_amt=200000

# Wait for signet confirmations (no local mining shortcut)
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet listchannels
```

SG: allow **19735** (or 9735 if remapped) from peers you need.

### 7) First payment

- Have a peer pay your invoice, or pay a peer invoice (amount ≥ `MIN_PAYMENT_SATS`, default 2000).
- Confirm `listpayments` / channel balances.

### 8) Health (signet)

```bash
LND_CONTAINER=agent-payment-decision-lnd-signet \
LND_NETWORK=signet \
REQUIRED_CONTAINERS=agent-payment-decision-lnd-signet \
BITCOIND_CONTAINER=none \
CHECK_LOOP=0 \
  ./check-aws-health.sh
```

### 9) Stop (keep wallet)

```bash
./shutdown-signet-aws.sh
# Destroy signet wallet only if intentional:
# docker compose -f docker-compose.signet.aws.yml down -v
```

---

## Option 1: dual-node (Mac + AWS) — recommended peer URI source

Run a second LND on the **Mac** on signet. You control both ends (like regtest).

| Role | Container | Host P2P port |
|------|-----------|---------------|
| Agent (AWS) | `agent-payment-decision-lnd-signet` | **19735** |
| Counterparty (Mac) | `agent-bitcoin-lnd-signet` | **29735** |

### Mac — start + sync

```bash
cd ~/agent-bitcoin
git pull origin main
chmod +x startup-signet-mac.sh shutdown-signet-mac.sh

# One-time if you previously ran Neutrino Mac LND (backend switch unsupported):
./shutdown-signet-mac.sh 2>/dev/null || true
docker volume ls | grep -i lnd-signet   # find name, then:
# docker volume rm <project>_agent-bitcoin-lnd-signet-data

./startup-signet-mac.sh
# create/unlock wallet; save seed (new wallet after wipe)

export MAC_LND=agent-bitcoin-lnd-signet
export MAC_BTC=agent-bitcoin-bitcoind-signet

# bitcoind first (source of truth for height):
docker exec "$MAC_BTC" bitcoin-cli -signet -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 \
  getblockchaininfo | grep -E '"blocks"|"headers"|"initialblockdownload"'

# LND tracks bitcoind after unlock:
docker exec "$MAC_LND" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo \
  | grep -E 'identity_pubkey|synced_to_chain|block_height'
```

**Progress check:**

1. **bitcoind** `blocks` should rise (toward ~300k+). First IBD can take a long time — keep Mac awake and Docker running.
2. **LND** `block_height` should follow bitcoind once unlocked (not stay at 0 while bitcoind advances).
3. When bitcoind `initialblockdownload` is false and LND `synced_to_chain` is true, connect to AWS.

Mac does **not** need faucet funds if **AWS opens** the channel (AWS already has ~100k).

### Mac bitcoind stuck / LND height 0

1. Confirm both containers **Up**: `docker ps --filter name=agent-bitcoin`
2. bitcoind logs / peers:
   ```bash
   docker logs --tail 50 agent-bitcoin-bitcoind-signet
   docker exec agent-bitcoin-bitcoind-signet bitcoin-cli -signet \
     -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 getconnectioncount
   docker exec agent-bitcoin-bitcoind-signet bitcoin-cli -signet \
     -rpcuser=lightning -rpcpassword=lightning -rpcport=38332 getblockcount
   ```
3. LND should talk to `bitcoind-signet:38332` over the compose network:
   ```bash
   docker logs --tail 50 agent-bitcoin-lnd-signet | grep -iE 'BTCD|bitcoind|Waiting for chain|error'
   ```
4. Keep the Mac **awake** (sleep freezes Docker).
5. If you migrated from Neutrino without wiping LND volume: wipe LND volume and recreate wallet (see above).

### Mac — get your peer identity (the URI pieces)

```bash
docker exec "$MAC_LND" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo \
  | grep identity_pubkey
# Save as MAC_PUB=02...
```

You usually **do not** need Mac’s public IP: Mac will **connect out** to AWS (like regtest).

### Mac — connect to AWS (outbound)

```bash
AWS_EIP=3.90.159.146
AWS_PUB=02102808588d8aece7e27af6eb5843810d04ffd88975136e3045e0ed4d45efebea
# Use YOUR current AWS signet pubkey if different:
# docker exec agent-payment-decision-lnd-signet lncli ... getinfo | grep identity

docker exec "$MAC_LND" lncli --lnddir=/home/lnd/.lnd --network=signet \
  connect ${AWS_PUB}@${AWS_EIP}:19735

docker exec "$MAC_LND" lncli --lnddir=/home/lnd/.lnd --network=signet listpeers
```

AWS security group must allow **inbound TCP 19735** from your Mac’s public IP (or temporarily broader for lab).

### AWS — confirm peer + open channel

```bash
export LND_CONTAINER=agent-payment-decision-lnd-signet

docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet listpeers

# MAC_PUB from Mac getinfo (hex only, no @host)
MAC_PUB=<paste-mac-identity-pubkey>

docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet \
  openchannel --node_key="$MAC_PUB" --local_amt=50000

# Wait for signet confirmations (hours possible):
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet pendingchannels
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet listchannels
```

When `active: true`, AWS has **outbound**; Mac has **inbound**. First easy payment: **AWS pays a Mac invoice**.

```bash
# Mac — invoice
docker exec agent-bitcoin-lnd-signet lncli --lnddir=/home/lnd/.lnd --network=signet \
  addinvoice --amt=2000 --memo='signet-dual'

# AWS — pay (paste bolt11)
docker exec agent-payment-decision-lnd-signet lncli --lnddir=/home/lnd/.lnd --network=signet \
  payinvoice --force '<bolt11>'
```

### Stop Mac signet

```bash
./shutdown-signet-mac.sh
```

---

## Later (not v1)

| Item | Notes |
|------|--------|
| Nostr Phase B on signet | Same scripts; `LND_NETWORK=signet` + container names |
| Loop Autoloop | Research public Loop/signet; keep regtest tools for now |
| Mainnet | Separate design, `AGENT_BITCOIN_ALLOW_MAINNET=1`, never implicit |

---

## Pitfalls

| Issue | Fix |
|-------|-----|
| `Unsupported LND_NETWORK=signet` | Pull code that allows signet; set env |
| Empty `--externalip` crash after unlock | Always pass EIP to `startup-signet-aws.sh` |
| Port conflict with regtest | Use compose host ports 19735/20009 or stop regtest |
| Wallet on wrong network | Separate volume `agent-bitcoin_lnd-signet-data` only |
| Sync stuck (Mac) | Check **bitcoind** `getblockcount` first; then LND; wipe LND volume if you switched from Neutrino |
| Sync stuck (AWS Neutrino) | Check Neutrino peers in AWS compose; logs; patience |
| No route / no channel | Open channel; wait confs; check peers |

---

## Quick env cheat sheet

```bash
export AWS_IP=3.90.159.146
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_DIR=/home/lnd/.lnd
```
