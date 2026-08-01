# Signet dress rehearsal (Phase 7)

**Goal:** Run the mainnet **pilot procedure** on **signet**, end-to-end, before any real funds.
**Not:** mainnet go-live (that is Phase 8, separate decision).

**Audience:** Operator (topology B).
**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [daily-ops-signet.md](./daily-ops-signet.md) · [lnd-client.md](./lnd-client.md) · [security-hardening.md](./security-hardening.md) · [liquidity-topology-b.md](./liquidity-topology-b.md)

---

## What “as if mainnet” means on signet

| Pilot rule | How we simulate on signet |
|------------|---------------------------|
| gRPC client | `LND_TRANSPORT=grpc` + cert/macaroon |
| Single pay ≤ 50k | `MAX_PAYMENT_SATS=50000` |
| Daily sum ≤ 100k | `MAX_DAILY_PAYMENT_SATS=100000` |
| Autopay deliberate | Set `AGENT_BITCOIN_ALLOW_AUTOPAY=1` only while paying (practice the flag) |
| No on-chain fee path | Do **not** call `/send-fee` or `collect_transaction_fee` |
| Human unlock | No auto-unlock; unlock yourself after restart |
| Dual-node | Mac ↔ AWS channel active |
| Backup | Export + verify SCB before and after |

---

## Pre-flight (both hosts)

- [ ] `git pull origin main` on Mac and AWS
- [ ] Phase 6 checklist done (secrets offline, SG OK, AMI private)
- [ ] Note start time: __________

---

## Part A — Env “pilot mode” (copy-paste)

### Mac (peer / often invoice creator)

```bash
cd ~/agent-bitcoin
export LND_NETWORK=signet
export LND_TRANSPORT=grpc
export LND_GRPC_HOST=127.0.0.1 LND_GRPC_PORT=30009
export LND_TLS_CERT_PATH="$HOME/.lnd-export/signet-mac/tls.cert"
export LND_MACAROON_PATH="$HOME/.lnd-export/signet-mac/admin.macaroon"
export MAX_PAYMENT_SATS=50000 MAX_DAILY_PAYMENT_SATS=100000
export AGENT_BITCOIN_SPEND_LEDGER="$HOME/.config/agent-bitcoin/dress-rehearsal-spend.json"
# Re-export certs if missing:
# MAC_LND=agent-bitcoin-lnd-signet
# mkdir -p "$HOME/.lnd-export/signet-mac"
# docker cp "$MAC_LND:/home/lnd/.lnd/tls.cert" "$HOME/.lnd-export/signet-mac/tls.cert"
# docker cp "$MAC_LND:/home/lnd/.lnd/data/chain/bitcoin/signet/admin.macaroon" "$HOME/.lnd-export/signet-mac/admin.macaroon"
```

### AWS (agent / often payer)

```bash
cd ~/agent-bitcoin
export LND_NETWORK=signet
export LND_TRANSPORT=grpc
export LND_GRPC_HOST=127.0.0.1 LND_GRPC_PORT=20009
export LND_TLS_CERT_PATH="$HOME/.lnd-export/signet-aws/tls.cert"
export LND_MACAROON_PATH="$HOME/.lnd-export/signet-aws/admin.macaroon"
export MAX_PAYMENT_SATS=50000 MAX_DAILY_PAYMENT_SATS=100000
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
export AGENT_BITCOIN_SPEND_LEDGER="$HOME/.config/agent-bitcoin/dress-rehearsal-spend.json"
# Export certs if missing:
# AWS_LND=agent-payment-decision-lnd-signet
# mkdir -p "$HOME/.lnd-export/signet-aws"
# docker cp "$AWS_LND:/home/lnd/.lnd/tls.cert" "$HOME/.lnd-export/signet-aws/tls.cert"
# docker cp "$AWS_LND:/home/lnd/.lnd/data/chain/bitcoin/signet/admin.macaroon" "$HOME/.lnd-export/signet-aws/admin.macaroon"
```

Optional helper (prints the same exports):

```bash
./signet-dress-rehearsal-env.sh mac
./signet-dress-rehearsal-env.sh aws
# eval "$(./signet-dress-rehearsal-env.sh mac)"   # if you want to source
```

---

## Part B — Simulated restart (AMI-like)

Do **not** need a full EC2 stop if unlock practice is enough; full reboot is stronger.

### B1. Backup before “disruption”

```bash
# Mac
export LND_CONTAINER=agent-bitcoin-lnd-signet LND_NETWORK=signet
./export-lnd-backup.sh && ./verify-lnd-backup.sh ~/lnd-backups/agent-bitcoin-lnd-signet/signet/<latest>

# AWS
export LND_CONTAINER=agent-payment-decision-lnd-signet LND_NETWORK=signet
./export-lnd-backup.sh && ./verify-lnd-backup.sh ~/lnd-backups/agent-payment-decision-lnd-signet/signet/<latest>
```

- [ ] Mac backup VERIFY pass
- [ ] AWS backup VERIFY pass

### B2. Restart LND (minimum) or host

**Minimum (restart containers):**

```bash
# Mac
./shutdown-signet-mac.sh
./startup-signet-mac.sh
# unlock when prompted

# AWS
docker restart agent-payment-decision-lnd-signet
docker exec -it agent-payment-decision-lnd-signet \
  lncli --lnddir=/home/lnd/.lnd --network=signet unlock
```

**Stronger:** reboot AWS instance (AMI-like), then unlock after boot.

- [ ] Both wallets unlocked by human
- [ ] No auto-unlock used

### B3. Health + peer

```bash
# Mac
./update-aws-sg-my-ip.sh   # if IP may have changed
./wait-mac-lnd.sh          # or wait until synced
export LND_CONTAINER=agent-bitcoin-lnd-signet
export AWS_EIP=<your-eip>
export AWS_PUB=02102808588d8aece7e27af6eb5843810d04ffd88975136e3045e0ed4d45efebea
docker exec "$LND_CONTAINER" lncli --lnddir=/home/lnd/.lnd --network=signet \
  connect ${AWS_PUB}@${AWS_EIP}:19735
./check-signet-health.sh --role mac

# AWS
./check-signet-health.sh --role aws
```

- [ ] Mac health HEALTHY or OK_WITH_WARNINGS (channel active)
- [ ] AWS health HEALTHY or OK_WITH_WARNINGS (channel active)

---

## Part C — gRPC + pilot limits + pay

### C1. gRPC getinfo both sides

```bash
# with Part A env set on each host
uv run python -c "from agent_bitcoin.lightning import create_lnd_client; c=create_lnd_client(); print(c.transport, c.get_info().get('identity_pubkey'), c.get_info().get('synced_to_chain'))"
```

- [ ] Mac: `grpc` + expected Mac pubkey
- [ ] AWS: `grpc` + expected AWS pubkey

### C2. Policy smoke (no pay yet)

```bash
# AWS — without AUTOPAY should fail on mainnet; on signet with ALLOW_AUTOPAY=0:
export AGENT_BITCOIN_ALLOW_AUTOPAY=0
uv run python -c "from agent_bitcoin import create_client; create_client().pay_invoice('lnbogus')"
# expect RuntimeError ALLOW_AUTOPAY — then:
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
```

- [ ] Kill-switch behavior understood

### C3. Product-path pay (pilot amount)

Use **2000** sats (min). Prefer file/scp for bolt11 (avoid wrap).

```bash
# Mac — create via gRPC SDK (AgentBitcoinClient)
export AGENT_BITCOIN_ALLOW_AUTOPAY=1   # only needed if you set =0 above; lab default allows pay
uv run python -c "
from agent_bitcoin import create_client
from pathlib import Path
c = create_client()
inv = c.create_invoice('dress-rehearsal', 2000)
Path('/tmp/signet-bolt11.txt').write_text(inv.payment_request + '\n')
print(inv.payment_request[:40], '...')
"
scp -i ~/.ssh/aws/agent-bitcoin-key.pem /tmp/signet-bolt11.txt ubuntu@<AWS_EIP>:/tmp/signet-bolt11.txt

# AWS — pay via gRPC + pilot limits + spend ledger
export AGENT_BITCOIN_ALLOW_AUTOPAY=1
uv run python -c "
from pathlib import Path
from agent_bitcoin import create_client
b = ''.join(Path('/tmp/signet-bolt11.txt').read_text().split())
r = create_client().pay_invoice(b)
print(r)
print(create_client().get_channel_balance())
"
```

- [ ] Pay `success=True`
- [ ] Balances moved
- [ ] Did **not** run `/send-fee`

### C4. Backup after pay

```bash
# both hosts again
./export-lnd-backup.sh
```

- [ ] Post-pay export done

---

## Part D — Record results

| Item | Result |
|------|--------|
| Date (UTC) | |
| Restart type (container / host reboot) | |
| Mac health | |
| AWS health | |
| gRPC Mac / AWS | |
| Pay success | |
| Issues found | none / list: |
| Actual time unlock→pay (RTO-ish) | |

**Pass criteria (Phase 7 exit):**

- [ ] Restart → unlock → health → peer → gRPC → limited pay succeeded
- [ ] Backups verified before and after
- [ ] Fee path not used
- [ ] No critical issues open (or written and fixed)

If anything failed: fix on signet, re-run the failed section, then mark complete.

---

## After Phase 7

You are **eligible to decide** on Phase 8 (mainnet pilot). Phase 8 is **not** automatic:

- New mainnet wallets/volumes
- Tiny channel ≤ 500k
- Human-attended pays only
- Explicit go/no-go

---

## Phase 7 deliverables (repo)

- [x] This runbook
- [x] `signet-dress-rehearsal-env.sh` helper
- [ ] Operator completes checklist above (your session)
