# Signet operator guide (v1)

**Audience:** Operators moving from private **regtest** to public **signet**.
**Agents / SDK:** still do **not** open channels or run Loop. Payment agents stay invoice / pay / decide.

**Related:** [backend.md](./backend.md) (regtest ops) · [liquidity-automation.md](./liquidity-automation.md) · [mainnet-pilot.md](./mainnet-pilot.md) (readiness scope only) · [SECURITY.md](../SECURITY.md)

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

### 5) Backend / SDK (see **Product path** below after channel is up)

Env for AWS agent LND:

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_DIR=/home/lnd/.lnd
export AGENT_BITCOIN_API_KEY=...   # from .env for HTTP API
```

Full dual-node create/pay without typing `lncli` is documented in **Product path: SDK/API**.

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

- Have a peer pay your invoice, or pay a peer invoice (amount ≥ `MIN_PAYMENT_SATS`, default 1000).
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

# Or poll until ready (auto-detects signet container — no network arg):
# ./wait-mac-lnd.sh
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

## Product path: SDK/API

Goal: create and pay signet invoices through **agent-bitcoin** (SDK and/or HTTP API), not by typing `lncli addinvoice` / `payinvoice`. Requires an **active dual-node channel** (above).

### Who runs where

The SDK uses **local** `docker exec`. Run each step on the host that has that container:

| Role | Host | `LND_CONTAINER` |
|------|------|-----------------|
| Mac LND (often **receiver**) | Mac | `agent-bitcoin-lnd-signet` |
| AWS LND (often **payer** — has channel outbound) | AWS | `agent-payment-decision-lnd-signet` |

Primary success direction (AWS holds most liquidity): **Mac creates → AWS pays**.

### Prerequisites

- Daily Mac: `./update-aws-sg-my-ip.sh` then connect if needed
- AWS: unlock LND if locked
- Both: `synced_to_chain` and `listchannels` → `"active": true`
- Amount ≥ `MIN_PAYMENT_SATS` (default **1000**)

Record balances before/after:

```bash
# each host with its container
export LND_NETWORK=signet LND_DIR=/home/lnd/.lnd
export LND_CONTAINER=...   # Mac or AWS name
uv run python examples/signet_product_path.py balance
```

### A) SDK create (Mac)

```bash
cd ~/agent-bitcoin   # repo root
export LND_NETWORK=signet
export LND_CONTAINER=agent-bitcoin-lnd-signet
export LND_DIR=/home/lnd/.lnd

uv run python examples/signet_product_path.py create --amount 2000 --memo 'signet-sdk-product'
# copy payment_request=lntbs...
```

### B) SDK pay (AWS)

```bash
cd ~/agent-bitcoin
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_DIR=/home/lnd/.lnd
export BOLT11='lntbs...'   # from Mac create

uv run python examples/signet_product_path.py pay --bolt11 "$BOLT11"
uv run python examples/signet_product_path.py balance
```

**Pass:** `success=True`; Mac local balance up ~2000; AWS local down ~2000.

### C) HTTP API pay (AWS)

Set env **before** starting uvicorn (`LNDClient` is created at import):

```bash
export LND_NETWORK=signet
export LND_CONTAINER=agent-payment-decision-lnd-signet
export LND_DIR=/home/lnd/.lnd
export AGENT_BITCOIN_API_KEY=...   # same as .env

uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
curl -s http://127.0.0.1:8000/
curl -s -X POST http://127.0.0.1:8000/pay \
  -H "X-API-Key: $AGENT_BITCOIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"payment_request\":\"$BOLT11\",\"fee_limit_sats\":500}"
```

Create via API (invoice lands on **AWS** LND):

```bash
curl -s -X POST http://127.0.0.1:8000/invoices \
  -H "X-API-Key: $AGENT_BITCOIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"memo":"signet-api","amount_sats":2000}'
# Mac may pay only if it has enough local balance (often ~2000 after first hop)
```

### Success checklist

- [ ] Invoice created via SDK or `POST /invoices` (no hand-typed `lncli addinvoice`)
- [ ] Payment via SDK or `POST /pay` (no hand-typed `lncli payinvoice`)
- [ ] Channel balances moved
- [ ] Optional: reverse hop (AWS invoice → Mac pay) if Mac has local sats

---

### Daily ops and health

Full checklist: **[daily-ops-signet.md](./daily-ops-signet.md)**.

```bash
./check-signet-health.sh --role mac   # on Mac
./check-signet-health.sh --role aws   # on AWS
```

### Daily restart order (Mac)

Home public IP often changes overnight. **Do this first** before connect:

```bash
./update-aws-sg-my-ip.sh          # allows your current IP on SG (incl. 19735 signet P2P)
# optional: ./update-aws-sg-my-ip.sh --dry-run
```

Then start/wait Mac stack, then connect (below). Skip the SG step only if you know your IP is unchanged and `nc -vz $AWS_EIP 19735` already succeeds.

Does **not** affect: Mac bitcoind sync, local LND unlock, or channel funds on-chain. Only **inbound** AWS ports from the Mac (SSH, API, regtest/signet LND P2P, etc.).

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

AWS security group must allow **inbound TCP 19735** from your Mac’s public IP — kept current by `./update-aws-sg-my-ip.sh`.

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

## Nostr Phase B on signet (same as regtest)

**Status (2026-08-02):** Live dual-host exercised — signed bus coordination + **2000 sat** Lightning pay settled on the signet channel (Mac payer → AWS invoice).

Same scripts and protocol as regtest Phase B ([nostr-agent-identity.md](./nostr-agent-identity.md)); only network + container names change. File bus remains the lab coordination path (public relays optional).

### Prerequisites

- Mac + AWS signet stacks up, wallets unlocked, **peer connected**, **channel active**
- Python 3.12 + `.[nostr]` on both hosts that sign (`uv venv -p 3.12 .venv-nostr`)
- Shared `NOSTR_PASSPHRASE` and shared bus/keys (rsync/scp `.nostr-poc-signet/`)
- Payer has enough **local** channel balance (amount ≥ `MIN_PAYMENT_SATS`, default 1000)

### Env (signet containers)

```bash
export LND_NETWORK=signet
export LND_PAYER_CONTAINER=agent-bitcoin-lnd-signet          # Mac
export LND_INVOICE_CONTAINER=agent-payment-decision-lnd-signet  # AWS
export NOSTR_PASSPHRASE='use-a-strong-passphrase'
export NOSTR_POC_DIR=./.nostr-poc-signet   # gitignored; keep separate from regtest .nostr-poc
```

### Live dual-host (small amount)

```bash
# --- Mac (payer): request ---
.venv-nostr/bin/python examples/nostr_phase_b_payment.py \
  --dir "$NOSTR_POC_DIR" --passphrase "$NOSTR_PASSPHRASE" \
  request --amount 2000 --memo 'nostr-signet-b'

# Sync keys + bus to AWS (first run needs full tree; later bus is enough if keys already there)
rsync -az -e "ssh -i ~/.ssh/aws/agent-bitcoin-key.pem -o IdentitiesOnly=yes" \
  "$NOSTR_POC_DIR"/ ubuntu@${AWS_IP}:~/agent-bitcoin/.nostr-poc-signet/

# --- AWS (invoice / receive) ---
ssh -i ~/.ssh/aws/agent-bitcoin-key.pem -o IdentitiesOnly=yes ubuntu@${AWS_IP} \
  "cd ~/agent-bitcoin && export LND_NETWORK=signet \
   LND_INVOICE_CONTAINER=agent-payment-decision-lnd-signet && \
   .venv-nostr/bin/python examples/nostr_phase_b_payment.py \
     --dir ./.nostr-poc-signet --passphrase '$NOSTR_PASSPHRASE' invoice"

# Offer bus file back to Mac
rsync -az -e "ssh -i ~/.ssh/aws/agent-bitcoin-key.pem -o IdentitiesOnly=yes" \
  ubuntu@${AWS_IP}:~/agent-bitcoin/.nostr-poc-signet/bus/ "$NOSTR_POC_DIR/bus/"

# --- Mac (pay) ---
.venv-nostr/bin/python examples/nostr_phase_b_payment.py \
  --dir "$NOSTR_POC_DIR" --passphrase "$NOSTR_PASSPHRASE" pay

.venv-nostr/bin/python examples/nostr_phase_b_payment.py \
  --dir "$NOSTR_POC_DIR" --passphrase "$NOSTR_PASSPHRASE" status
```

### Proven exercise (lab note)

| Field | Value |
|-------|--------|
| Date | 2026-08-02 |
| Amount | 2000 sats |
| Direction | Mac `agent-bitcoin-lnd-signet` → AWS `agent-payment-decision-lnd-signet` |
| Payment hash | `738acaa3319fbf094273960cf1263fcee0bd63291023332efa1715b55cb2c740` |
| LND status | `SUCCEEDED` (fee 0 on direct channel) |
| Coordination | signed `pay_request` / `invoice_offer` / `payment_result` file bus |

Dry-run (no LND) still works on any host with the same scripts.

---

## Later (not v1)

| Item | Notes |
|------|--------|
| Loop Autoloop | Research public Loop/signet; keep regtest tools for now |
| Mainnet | Separate design, `AGENT_BITCOIN_ALLOW_MAINNET=1`, never implicit |
| Nostr NWC / NIP-46 over relays | Roadmap in [nostr-agent-identity.md](./nostr-agent-identity.md) Phase C+ |

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
