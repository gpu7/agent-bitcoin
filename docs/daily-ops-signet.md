# Daily ops — signet dual-node (Phase 4)

**Audience:** Operator (topology B).
**Related:** [signet.md](./signet.md) · [mainnet-pilot.md](./mainnet-pilot.md) · [lnd-backup-restore.md](./lnd-backup-restore.md)

---

## One-command health

```bash
# Mac
./check-signet-health.sh --role mac

# AWS
./check-signet-health.sh --role aws

# Auto-detect from running containers
./check-signet-health.sh
```

Exit **0** = healthy or warnings only. Exit **1** = unhealthy.

Optional:

```bash
./check-signet-health.sh --json
HEALTH_LOG=~/lnd-backups/health.log ./check-signet-health.sh --role mac
# on fail only:
HEALTH_WEBHOOK_URL='https://hooks.slack.com/…' ./check-signet-health.sh --role aws
```

Cron example (no auto-unlock — password stays human):

```cron
*/30 * * * * cd /home/ubuntu/agent-bitcoin && ./check-signet-health.sh --role aws >>/var/log/signet-health.log 2>&1
```

---

## Start of day (Mac + AWS)

| Step | Where | Command / action |
|------|--------|------------------|
| 1 | Mac | `./update-aws-sg-my-ip.sh` |
| 2 | AWS | Unlock if needed: `docker exec -it agent-payment-decision-lnd-signet lncli --lnddir=/home/lnd/.lnd --network=signet unlock` |
| 3 | Mac | Start stack if stopped: `./startup-signet-mac.sh` → unlock |
| 4 | Mac | `./wait-mac-lnd.sh` (or health until synced) |
| 5 | Mac | Connect: `export LND_CONTAINER=agent-bitcoin-lnd-signet AWS_EIP=… AWS_PUB=02102808…` then `lncli … connect ${AWS_PUB}@${AWS_EIP}:19735` |
| 6 | Both | `./check-signet-health.sh --role mac` / `--role aws` → **RESULT: HEALTHY** or OK_WITH_WARNINGS |
| 7 | Either | Work: SDK product path, tests, etc. |

Default peer pubkeys in the health script match the lab identities documented in signet ops (override with `EXPECT_PEER_PUBKEY=` if you recreate wallets).

---

## Common fixes

| Symptom | Fix |
|---------|-----|
| `wallet locked` | `docker exec -it $LND_CONTAINER lncli … unlock` |
| `no peers` / `zero active channels` | Mac connect to AWS; AWS unlocked; SG TCP **19735** from Mac IP |
| `i/o timeout` on connect | `./update-aws-sg-my-ip.sh` |
| bitcoind IBD (Mac) | Wait; keep Mac awake |
| Health UNHEALTHY after reboot | Unlock both; reconnect; re-run health |

---

## End of day

| Step | Where | Action |
|------|--------|--------|
| 1 | Mac | Prefer `./shutdown-signet-mac.sh` (avoid sleep with Docker up) |
| 2 | AWS | Leave instance up if desired; LND may stay running |
| 3 | Either | Optional: `./export-lnd-backup.sh` after channel changes |

---

## Phase 4 exit

- [x] `check-signet-health.sh` for Mac and AWS roles
- [x] Daily SOP documented
- [x] Optional log + webhook hooks
- [ ] Operator ran health green on Mac and AWS after unlock/connect
