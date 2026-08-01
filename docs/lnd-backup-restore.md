# LND backup and restore (Phase 3)

**Audience:** Operators (topology B: Mac + AWS).
**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [signet.md](./signet.md) · [SECURITY.md](../SECURITY.md)

**Goal:** Survive host loss or disk failure without losing channel state process.
**Does not** replace offline seed + wallet password custody.

---

## What to back up

| Artifact | Purpose | Secret? |
|----------|---------|---------|
| **Seed + wallet password** | Recreate wallet | **Yes — offline only** |
| **`channel.backup` (SCB)** | Recover channels after wallet restore | Sensitive; encrypt off-host |
| **Docker volume** (`*.lnd` data) | Full node state (fastest restore if volume intact) | **Yes** |
| TLS cert | gRPC clients | Low |
| Admin macaroon | Full node control | **Yes — avoid bulk backup if possible** |

Never commit backups to git. Prefer encrypted disk / password manager attachment / offline media.

---

## RTO / RPO (pilot targets)

| Metric | Pilot target | Meaning |
|--------|--------------|---------|
| **RPO** | ≤ 24h | Max data loss: take SCB **daily** (or after every channel open/close) |
| **RTO** | ≤ 4h | Time to restore on a new host and reconnect peer (human present) |

Tighten before mainnet Phase 8 if you need better.

---

## Export (safe while node is running)

### Scripts

```bash
# Mac peer (signet)
export LND_CONTAINER=agent-bitcoin-lnd-signet LND_NETWORK=signet
./export-lnd-backup.sh
./verify-lnd-backup.sh ~/lnd-backups/agent-bitcoin-lnd-signet/signet/<timestamp>

# AWS agent (signet) — run on AWS
export LND_CONTAINER=agent-payment-decision-lnd-signet LND_NETWORK=signet
./export-lnd-backup.sh
```

Optional full volume snapshot (larger):

```bash
SNAPSHOT_VOLUME=1 ./export-lnd-backup.sh
```

### Schedule (operator)

- After **every** channel open/close: `./export-lnd-backup.sh` on **both** hosts
- Daily: same (cron optional; do not put seeds in cron logs)
- Before AMI / host maintenance: export + verify

---

## Restore paths

### A) Preferred — restore Docker volume from `lnd-volume.tgz`

Use when you have a recent volume tarball and the same network (signet/mainnet).

1. Stop LND (and bitcoind if local): e.g. `./shutdown-signet-mac.sh` or compose down.
2. Create/replace volume (names depend on compose project — check `docker volume ls`).
3. Extract:
   ```bash
   docker volume create NEW_VOLUME_NAME
   docker run --rm \
     -v NEW_VOLUME_NAME:/lnddata \
     -v /path/to/backup:/backup:ro \
     alpine:3.20 \
     sh -c 'cd /lnddata && tar xzf /backup/lnd-volume.tgz'
   ```
4. Point compose at that volume (or rename volumes carefully).
5. Start stack, **unlock** wallet, check `getinfo` / `listchannels`.
6. Mac → AWS `connect` if peers dropped.

### B) SCB recovery — new wallet from seed + channel.backup

Use when volume is lost but you have **seed** + **channel.backup**.

1. New empty LND data dir / volume (same network).
2. `lncli create` (or create with recovery window if your LND version supports it).
3. Unlock.
4. Place SCB and restore, e.g.:
   ```bash
   # paths illustrative — use your LND_DIR and network
   docker cp /path/to/channel.backup CONTAINER:/tmp/channel.backup
   docker exec -it CONTAINER lncli --lnddir=/home/lnd/.lnd --network=signet \
     restorechanbackup --multi_file=/tmp/channel.backup
   ```
5. Wait for chain sync and channel recovery; may need force-close cooperation depending on state.
6. Re-export SCB after recovery.

Exact `restorechanbackup` flags vary slightly by LND version — confirm with:

```bash
docker exec CONTAINER lncli restorechanbackup --help
```

### C) Do not

- Reuse regtest/signet wallets on mainnet
- Publish AMI containing unlocked wallet or world-readable backups
- Rely only on AWS EBS snapshots without testing restore

---

## Signet restore drill (operator checklist)

Run when you have time; **prefer a throwaway node** if you do not want risk on the live dual-node channel. Record date in [mainnet-pilot.md](./mainnet-pilot.md).

1. [ ] `./export-lnd-backup.sh` on the node under test; `./verify-lnd-backup.sh` **PASS**
2. [ ] Seed + password confirmed offline (without opening the backup dir in chat/logs)
3. [ ] Either:
   - **Volume drill:** stop → restore tarball to a **new** volume name → start → unlock → `listchannels` / peer connect
   - **SCB drill:** new empty volume → create from seed → restorechanbackup → sync
4. [ ] Peer reconnect (Mac↔AWS) if dual-node
5. [ ] Small SDK pay or invoice create works
6. [ ] Note issues / duration (actual RTO)
7. [ ] Delete temporary volumes after drill

**Live dual-node risk:** restoring the *production* signet volume incorrectly can force-close or brick the channel. Prefer cloning to a second machine or a new volume name first.

---

## Topology B notes

| Host | Container (signet) | Volume (typical) |
|------|--------------------|------------------|
| Mac | `agent-bitcoin-lnd-signet` | `*_agent-bitcoin-lnd-signet-data` |
| Mac | `agent-bitcoin-bitcoind-signet` | bitcoind volume (chain — separate backup if needed) |
| AWS | `agent-payment-decision-lnd-signet` | `agent-bitcoin_lnd-signet-data` or compose name |

Back up **both** LND nodes. Bitcoind can re-sync from network (time cost); LND channel state cannot.

---

## Phase 3 exit criteria

- [x] Export script + verify script in repo
- [x] This runbook
- [ ] Operator has run export+verify on Mac **and** AWS at least once
- [ ] Operator has completed restore drill checklist (or scheduled date)
- [x] RPO/RTO targets written
