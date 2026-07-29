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
| `docker-compose.signet.mac.yml` | Neutrino LND on Mac signet (dual-node peer) |
| `startup-signet-aws.sh` / `shutdown-signet-aws.sh` | AWS start/stop (keep volume) |
| `startup-signet-mac.sh` / `shutdown-signet-mac.sh` | Mac start/stop (keep volume) |
| `LND_NETWORK=signet` | SDK / `LNDClient` |
| `LND_CONTAINER=...` | e.g. `agent-payment-decision-lnd-signet` |

**Does not** replace or delete regtest compose/scripts. Do **not** reuse regtest wallet volumes for signet.

---

## Topology (v1 recommendation)

```text
AWS: agent-payment-decision-lnd-signet  (P2P host :19735)
        |
   Lightning channel (signet)
        |
Mac: agent-bitcoin-lnd-signet           (P2P host :29735)
```

- **AWS host ports:** `19735` (P2P), `20009` (RPC) — avoid regtest `9735` / `10009`.
- **Mac host ports:** `29735` (P2P), `30009` (RPC) — avoid regtest Mac `9736` / `10010`.
- Prefer **Mac → AWS connect** (outbound from home network).

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
./startup-signet-mac.sh
# create/unlock wallet; save seed

export MAC_LND=agent-bitcoin-lnd-signet
# Wait until synced (can take a while):
docker exec "$MAC_LND" lncli --lnddir=/home/lnd/.lnd --network=signet getinfo \
  | grep -E 'identity_pubkey|synced_to_chain|block_height'
```

**Progress check:** `block_height` should **rise** (toward AWS tip, often 300k+).
If height stays **0 for 15–30+ minutes**, you are stuck — see **Mac Neutrino stuck** below (do not wait hours).

Mac does **not** need faucet funds if **AWS opens** the channel (AWS already has ~100k).

### Mac Neutrino stuck at height 0

Neutrino is LND’s light chain backend (no local bitcoind). It must reach Bitcoin **signet** peers that serve headers/filters.

1. Confirm wallet unlocked and container **Up** (not Restarting).
2. Check peers/logs:
   ```bash
   docker logs --tail 80 agent-bitcoin-lnd-signet | grep -iE 'BTCN|CMGR|peer|unable|error'
   docker exec agent-bitcoin-lnd-signet sh -c 'nc -vz -w 5 192.241.222.63 38333 || true'
   ```
3. Pull latest compose (uses `neutrino.connect` + Docker DNS `8.8.8.8`) and recreate:
   ```bash
   cd ~/agent-bitcoin
   git pull origin main
   docker compose -f docker-compose.signet.mac.yml up -d --force-recreate
   docker exec -it agent-bitcoin-lnd-signet \
     lncli --lnddir=/home/lnd/.lnd --network=signet unlock
   watch -n 15 'docker exec agent-bitcoin-lnd-signet lncli --lnddir=/home/lnd/.lnd --network=signet getinfo 2>/dev/null | grep block_height'
   ```
4. Keep the Mac **awake** (sleep freezes Docker networking).
5. If height still **0** after another 20–30 minutes: park Mac signet (`./shutdown-signet-mac.sh`) and use **AWS-only** until bitcoind-signet backend is added (heavier fallback).

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
| Sync stuck | Check Neutrino peers in compose; logs; patience |
| No route / no channel | Open channel; wait confs; check peers |

---

## Quick env cheat sheet

```bash
export AWS_IP=3.90.159.146
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_DIR=/home/lnd/.lnd
```
