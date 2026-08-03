# Mainnet infrastructure design (Step 4 — pre–Phase 8)

**Status:** Design accepted for topology B pilot. **Compose scaffolding in repo.**
**Does not authorize funding or Phase 8 go-live.**
**Date:** 2026-08-03
**Audience:** Operator.

**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [security-hardening.md](./security-hardening.md) · [signet.md](./signet.md) · [lnd-backup-restore.md](./lnd-backup-restore.md)

---

## Goals

Ship a **mainnet dual-node (topology B)** stack that:

1. Reuses the mental model of signet (Mac ↔ AWS, Mac connects out, small channel)
2. Uses **bitcoind** (not Neutrino) on **both** hosts
3. Uses **new volumes only** — never regtest/signet wallet or chain data
4. Keeps gRPC and RPC **off the public internet**
5. Enforces pilot kill-switches via env when you eventually pay

---

## Topology

```text
AWS:  bitcoind (mainnet, pruned OK for pilot)
        └── RPC/ZMQ ──► agent-payment-decision-lnd-mainnet
                              │ P2P :9735 (SG: Mac /32 or peers you choose)
                              │ gRPC 127.0.0.1:10009 only
Mac:  bitcoind (mainnet, pruned OK for pilot)
        └── RPC/ZMQ ──► agent-bitcoin-lnd-mainnet
                              │ P2P host :39735 → container 9735
                              │ gRPC 127.0.0.1:40009 only
                              └── connect → AWS_PUB@AWS_EIP:9735
```

| Role | Host | Container | Volume (compose name) |
|------|------|-----------|------------------------|
| Agent LND | AWS | `agent-payment-decision-lnd-mainnet` | `agent-bitcoin_lnd-mainnet-data` |
| Agent bitcoind | AWS | `agent-payment-decision-bitcoind-mainnet` | `agent-bitcoin_bitcoind-mainnet-data` |
| Peer LND | Mac | `agent-bitcoin-lnd-mainnet` | `agent-bitcoin_agent-bitcoin-lnd-mainnet-data` (project-prefixed) |
| Peer bitcoind | Mac | `agent-bitcoin-bitcoind-mainnet` | `agent-bitcoin_agent-bitcoin-bitcoind-mainnet-data` |

**Hard rule:** Do **not** mount or rename signet/regtest volumes onto these services.

---

## Ports and security group

### Host ports

| Service | AWS host | Mac host | Public? |
|---------|----------|----------|---------|
| LND P2P | **9735** | **39735** → 9735 | AWS: Mac IP /32 (and any intentional peer). Not world unless you accept inbound. |
| LND gRPC | **127.0.0.1:10009** | **127.0.0.1:40009** | **Never** public SG |
| bitcoind RPC | **not published** (docker exec only) | **not published** (docker exec only) | **Never** public |
| bitcoind P2P | not published (outbound OK) | not published | Optional later; not required for dual-node LN |

Signet may keep using 19735/20009 and 29735/30009 — **stop signet LND** before binding mainnet **9735** on AWS if both would conflict.

### SG checklist (mainnet pilot)

| Port | Direction | Source |
|------|-----------|--------|
| 22 | inbound | Operator IP /32 |
| 9735 | inbound | Mac IP /32 (dual-node) |
| 10009 | inbound | **none** (localhost on instance only) |
| 8000 | inbound | Prefer **none**; SSH tunnel if backend needed |
| 8332 | inbound | **none** |

---

## Chain backend

| Decision | Choice |
|----------|--------|
| Backend | **bitcoind** both sides |
| Image | `bitcoin/bitcoin:28.0` (pin; bump deliberately) |
| Prune | **Default prune=550** for pilot disk (no `txindex`) |
| Full archival | Optional later; needs large EBS (hundreds of GB) |
| Neutrino on mainnet | **Not** default for this pilot (signet AWS Neutrino was lab-only) |

First mainnet IBD can take hours–days. Mac and AWS only need to agree on tip for the channel; both must reach `synced_to_chain=true` before funding.

---

## Credentials (never commit)

Set on each host **before** `docker compose up` (password manager → env / `.env` that is gitignored):

```bash
export MAINNET_BITCOIND_RPCUSER='…unique…'
export MAINNET_BITCOIND_RPCPASS='…unique strong…'
export AWS_IP='…eip…'   # AWS only, for LND --externalip
```

| Secret | Mainnet rule |
|--------|----------------|
| bitcoind RPC | Unique; **not** lab `lightning`/`lightning` |
| LND wallet password | New; offline backup |
| LND seed | New; offline only; create on first `lncli create` |
| API key | Rotated; env only |
| Macaroons | `~/.lnd-export/mainnet-{mac,aws}/` chmod 600 |

---

## Compose and scripts (repo)

| File | Purpose |
|------|---------|
| [docker-compose.mainnet.aws.yml](../docker-compose.mainnet.aws.yml) | AWS bitcoind + LND |
| [docker-compose.mainnet.mac.yml](../docker-compose.mainnet.mac.yml) | Mac bitcoind + LND |
| [startup-mainnet-aws.sh](../startup-mainnet-aws.sh) | Start AWS stack (requires `AWS_IP` + RPC env) |
| [startup-mainnet-mac.sh](../startup-mainnet-mac.sh) | Start Mac stack |
| [shutdown-mainnet-aws.sh](../shutdown-mainnet-aws.sh) | Stop AWS (volumes preserved) |
| [shutdown-mainnet-mac.sh](../shutdown-mainnet-mac.sh) | Stop Mac (volumes preserved) |

### Safe start order (still **no funds**)

1. Confirm disk free (AWS EBS sized for prune or full node).
2. Set RPC env vars + `AWS_IP`.
3. `./startup-mainnet-mac.sh` and `./startup-mainnet-aws.sh <EIP>`.
4. `lncli create` **new** wallets (never import signet seed).
5. Wait for both `synced_to_chain=true`.
6. Export SCB placeholders after wallet create (`export-lnd-backup.sh` with mainnet container names).
7. **Stop here** until Phase 8 go/no-go.

### Env for SDK (when Phase 8 approved only)

```bash
export LND_NETWORK=mainnet
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=0          # set 1 only for deliberate human pay
# do NOT set AGENT_BITCOIN_ALLOW_MAINNET_FEE
export MAX_PAYMENT_SATS=50000
export MAX_DAILY_PAYMENT_SATS=100000
export LND_TRANSPORT=grpc
# Mac example:
export LND_GRPC_HOST=127.0.0.1 LND_GRPC_PORT=40009
export LND_TLS_CERT_PATH=$HOME/.lnd-export/mainnet-mac/tls.cert
export LND_MACAROON_PATH=$HOME/.lnd-export/mainnet-mac/admin.macaroon
```

---

## Coexistence with signet / regtest

| Stack | May run with mainnet? |
|-------|------------------------|
| Signet Mac | Yes if ports differ (signet 29735/30009 vs mainnet 39735/40009). Disk heavy. |
| Signet AWS | Conflict on **9735** if mainnet uses 9735 — stop signet LND or remap. |
| Regtest | Prefer stopped; avoid wallet/volume confusion. |

Recommended for pilot day: **only mainnet** containers running on each host.

---

## Funding and channel (Phase 8 only — not Step 4)

Frozen pilot limits from [mainnet-pilot.md](./mainnet-pilot.md) (**tight first pilot**):

- **Max loss budget ≈ 50,000 sats** total (on-chain + channel on pilot nodes)
- First fund ≤ **50,000** sats combined
- Channel ≤ **50,000** sats (prefer ~40–45k so open fees fit under 50k)
- Pay ≤ **50,000** single / **50,000** daily sum (prefer first pays of 2k)
- Human unlock / open / pay
- Autoloop off; on-chain product fee off

Connect:

```bash
# Mac, after both synced and unlocked
docker exec agent-bitcoin-lnd-mainnet lncli --lnddir=/home/lnd/.lnd --network=mainnet \
  connect ${AWS_PUB}@${AWS_IP}:9735
```

---

## Backup

Same scripts as signet; set containers:

```bash
export LND_CONTAINER=agent-bitcoin-lnd-mainnet LND_NETWORK=mainnet
./export-lnd-backup.sh
# SNAPSHOT_VOLUME=1 for volume tarball after significant activity
```

Schedule: after wallet create, after channel open/close, daily during pilot.

---

## Disk and cost (operator planning)

| Host | Pruned pilot (approx) | Notes |
|------|------------------------|-------|
| AWS EBS | ≥ **50–100 GB** gp3 start | Monitor; grow if prune insufficient |
| Mac | ≥ **50 GB** free | Keep laptop awake during IBD |
| Full node | **400 GB+** | Not required for dual-node pilot |

---

## Step 4 exit criteria

- [x] Design documented (this file)
- [x] Compose + start/stop scripts in repo (scaffolding)
- [x] Ports / SG / volumes / “new volumes only” specified
- [x] bitcoind-both-sides decision recorded
- [x] Explicit: **no funding** until Phase 8 go/no-go
- [ ] Operator reviews this doc and agrees (session / offline)
- [ ] Optional dry run: `compose config` only (no IBD required for Step 4 exit)

---

## What Step 4 does **not** include

- Creating mainnet wallets
- IBD completion
- On-chain funding
- Opening channels
- Phase 8 approval

Those are **Step 5** (decision) then controlled go-live.
