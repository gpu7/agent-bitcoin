# Backend Management

Operator runbook for the AWS + Mac regtest stack (not the public SDK guide).
SDK users: see [SDK.md](../SDK.md). Product overview: [README.md](../README.md).

**Liquidity / Autoloop roadmap (simple overview):** [liquidity-automation.md](./liquidity-automation.md)
**Phase 2 Autoloop deep dive:** [loop-autoloop.md](./loop-autoloop.md)
**Signet (public test network):** [signet.md](./signet.md) — separate compose/volumes from regtest

---

## Current environment (operator)

Canonical AWS host for day-to-day ops. **Stop/start keeps this IP** while the Elastic IP stays associated with the instance primary ENI.

| Item | Value |
|------|--------|
| Region / AZ | `us-east-1` / `us-east-1a` |
| Elastic IP (EIP) | **`3.90.159.146`** |
| Use for | `startup-*.sh`, Mac LND bitcoind host, `connect-mac-to-aws.sh`, integration tests, SSH |

```bash
# Export for a shell session (optional)
export AWS_EIP=3.90.159.146
# alias used in examples below
export AWS_IP="$AWS_EIP"
```

Example commands with the current EIP:

```bash
./startup-aws.sh regtest 3.90.159.146
./startup-mac.sh regtest 3.90.159.146
./connect-mac-to-aws.sh 3.90.159.146 <pubkey-from-aws-getinfo>
uv run python tests/test_aws_integration.py --backend-url http://3.90.159.146:8000
```

Elsewhere in this doc, `<AWS_EIP>` means this address (update this section if the EIP ever changes).
Do **not** put the EIP in README/SDK; keep it here for operators.

After attaching or changing the EIP, restart AWS LND so `--externalip` matches:

```bash
./startup-aws.sh regtest 3.90.159.146
# unlock wallet when prompted
```

### Admin / Mac IP and security group

Inbound access (SSH, API, bitcoind RPC/ZMQ, LND P2P for regtest) should be limited to **your current public IP**, not the open internet.

Your home/Mac IP can change. From the **Mac** (with AWS CLI credentials that can edit the instance security group):

```bash
# Preview
./update-aws-sg-my-ip.sh --dry-run

# Apply: detect public IP, allow it on the SG, remove old CIDRs on those ports
./update-aws-sg-my-ip.sh
```

Defaults: region `us-east-1`, SG `sg-04e9e86b18199e18f`, ports `22 8000 18443 18444 28332 28333 9735`.
Override with `AWS_REGION`, `SG_ID`, `PORTS`, or `MY_IP` if needed.

**Safe order:** new IP is authorized **before** old rules are revoked (reduces lockout risk).
If you still get locked out: AWS Console → EC2 → Security Groups → temporarily allow your new IP on port 22.

After any IP change, re-check from the Mac:

```bash
nc -zv 3.90.159.146 22
nc -zv 3.90.159.146 18443
```

Do not commit personal IPs into the repo; the script stores the last IP under `~/.config/agent-bitcoin/last-sg-ip` locally only.

### Backend API authentication

The FastAPI backend (`backend/main.py`) protects `/balance`, `/invoices`, `/pay`, and `/send-fee` with an API key.

1. Generate a key (on any trusted machine):
   ```bash
   openssl rand -hex 32
   ```
2. Store it in the password manager and in **AWS** `~/agent-bitcoin/.env` (mode `600`):
   ```bash
   AGENT_BITCOIN_API_KEY=<paste-key-here>
   ```
3. Restart the backend process (tmux session `backend` or however you run it) so it loads the new env.
4. Call APIs with header `X-API-Key: <key>` (or `Authorization: Bearer <key>`).
5. Integration test from Mac:
   ```bash
   export AGENT_BITCOIN_API_KEY='...'   # same key
   uv run python tests/test_aws_integration.py --backend-url http://3.90.159.146:8000
   ```

If the key is missing on the server, protected routes return **503**. Wrong key → **401**.

Do not commit the real key. `.env.example` only documents the variable name.

### Lightning / Bitcoin node policy (regtest)

These rules reduce the chance of accidental real-network or high-risk misconfiguration:

| Policy | Practice |
|--------|----------|
| **Network** | Stock scripts and compose files are **regtest only**. `startup-aws.sh` / `startup-mac.sh` **refuse** `testnet` and `mainnet`. |
| **SDK LND client** | Defaults to `regtest`. `LND_NETWORK=mainnet` is refused unless `AGENT_BITCOIN_ALLOW_MAINNET=1` is set deliberately. |
| **RPC credentials** | Compose uses simple bitcoind RPC user/pass for **isolated regtest only** — never reuse on public networks. |
| **Wallet** | Unlock only when operating; store password/seed in a password manager; treat seeds shown in chat/logs as unfit for real funds. |
| **Macaroons** | Keep inside Docker volumes; do not commit or publish admin macaroons. Prefer least-privilege macaroons if exporting for remote tools. |
| **Published ports** | P2P/RPC/ZMQ/API gated by security group (Step 2). Do not open LND gRPC (`10009`) to the internet. |
| **Mainnet** | Separate design, credentials, and hosts — not a flag flip on this stack. |

Verify the live AWS node is still on regtest (after unlock):

```bash
docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo \
  | grep -E '"chains"|testnet|regtest|block_height|synced_to_chain'
```

### Host hardening (operator checklist)

On the AWS Ubuntu host (high level — details stay private):

- Keep the OS on a supported LTS release; apply security updates (`unattended-upgrades` recommended)
- SSH: public-key authentication only; disable password logins
- Rely on **security group least privilege** (Step 2) for published ports; do not re-open admin/RPC/API to `0.0.0.0/0`
- Docker: do not expose the Docker socket on the network; limit who is in the `docker` group
- Prefer encrypted EBS volumes for node data when creating new disks/AMIs
- After package upgrades that restart Docker, confirm `agent-payment-decision-lnd`, `bitcoind`, and the backend API are up again

### Operational security (process)

#### Shutdown vs reset

| Action | Use when | Effect |
|--------|----------|--------|
| `./shutdown-aws.sh` | Normal end of day / before AMI | Stops containers; **keeps** Docker volumes (chain + LND) |
| `./shutdown-mac.sh` | End of Mac session | Stops Mac LND compose |
| `startup-aws-reset.sh` or `docker compose … down --volumes` / Loop `regtest.sh stop` | **Only** intentional full wipe | Destroys chain/wallet data |

Never use volume-wiping stop as the default. Prefer AMI snapshots at known-good milestones.

#### Wallet unlock discipline

- Unlock LND only when you need RPC (`lncli unlock` interactively).
- Do not put wallet passwords in committed scripts, git, tickets, or chat.
- Avoid `echo password | lncli` (lands in shell history). Prefer interactive unlock.
- If a password or seed may have leaked, treat it as burned for any future real-funds use; create a new wallet when leaving pure regtest.

#### Dependency and image updates

- Host: keep `unattended-upgrades` enabled (security Step 3).
- Project: periodically `git pull`, `uv sync`, and review Docker image tags (LND, bitcoind) when upgrading.
- After Docker engine upgrades, re-check containers, unlock LND, and backend API health.

#### Incident response (high level)

If you suspect compromise (open API key, exposed SSH, stolen laptop, unexpected pays):

1. **Contain** — stop the backend process; consider instance stop; tighten SG if needed.
2. **Rotate** — new `AGENT_BITCOIN_API_KEY`; new SSH key if exposed; new wallet before any real funds.
3. **Revoke** — invalidate exported macaroons; do not reuse leaked material.
4. **Recover** — restore from a known-good AMI / volumes only if integrity is trusted; otherwise rebuild regtest stack.
5. **Review** — check CloudTrail/AWS login history, `docker ps`, unexpected processes, API access patterns.
6. **Document** privately (password manager note) what was rotated and when.

Do not post incident details or secrets in public GitHub issues. Security reports: see [SECURITY.md](../SECURITY.md).

#### Pre-session operator checklist

1. `./update-aws-sg-my-ip.sh` if home IP may have changed
2. Start AWS stack; unlock LND; confirm `synced_to_chain`
3. Backend running with `AGENT_BITCOIN_API_KEY` set
4. Mac: startup + wait + connect if needed
5. Smoke: `curl` health + authenticated `/balance`

#### End-of-session checklist

1. Mac `./shutdown-mac.sh`
2. AWS `./shutdown-aws.sh` (volume-preserving)
3. Optional AMI
4. EC2 stop (EIP retained if associated)

### Monitoring and health checks

#### Manual / cron health script

On the **AWS** host (after `git pull`):

```bash
cd ~/agent-bitcoin
chmod +x check-aws-health.sh
./check-aws-health.sh
```

What it checks (no secrets printed):

- Root disk usage (fail if ≥ 90%)
- Docker daemon
- Required containers: `bitcoind`, `agent-payment-decision-lnd`
- bitcoind block height
- LND unlock/sync status (warn if locked; fail on hard errors)
- **Channel liquidity floors** (Phase 1): each **active** channel’s `local_balance` (outbound) and `remote_balance` (inbound) vs configurable minimums
- Backend `GET /` liveness
- Optional: `GET /balance` if `AGENT_BITCOIN_API_KEY` is set in the environment

Exit code **0** = healthy (warnings allowed); **1** = unhealthy.

#### Channel capacity floors (receive-heavy node)

**Phase 1** of liquidity automation: [liquidity-automation.md](./liquidity-automation.md).

For a receive-heavy `agent-payment-decision-lnd`, **inbound** (`remote_balance`) is what lets you keep receiving. Prefer keeping good channels open and restoring inbound later (Phase 2 Autoloop), not closing channels when imbalanced.

| Env | Default | Meaning |
|-----|---------|---------|
| `CHANNEL_MIN_LOCAL_SATS` | `5000` | Warn if outbound (local) below this |
| `CHANNEL_MIN_REMOTE_SATS` | `5000` | Warn if inbound (remote) below this |
| `CHANNEL_LIQUIDITY_STRICT` | `0` | Set `1` to **FAIL** (exit 1) on floor breaches |
| `CHANNEL_MIN_ACTIVE` | `1` | Require ≥1 active channel (warn/fail if none) |

Examples:

```bash
# Defaults (warn only)
./check-aws-health.sh

# Stricter inbound floor for receive-heavy operation
CHANNEL_MIN_REMOTE_SATS=20000 CHANNEL_MIN_LOCAL_SATS=5000 ./check-aws-health.sh

# Treat liquidity breaches as unhealthy (cron alerts)
CHANNEL_LIQUIDITY_STRICT=1 ./check-aws-health.sh
```

Low **remote** → may fail to **receive** large invoices.
Low **local** → may fail to **send/pay** (less critical for receive-heavy, still reported).

Optional cron (every 15 minutes):

```bash
# crontab -e  (example — adjust paths)
*/15 * * * * cd /home/ubuntu/agent-bitcoin && ./check-aws-health.sh >> /home/ubuntu/agent-bitcoin-health.log 2>&1
```

JSON: `./check-aws-health.sh --json`

#### Backend access logs

The API logs method, path, status, and latency only (not API keys or invoice bodies). Auth failures log at warning. Invoice/pay/fee log amounts and payment_hash/txid where useful—not full BOLT11.

```bash
tmux attach -t backend
```

#### What to watch for

| Signal | Concern |
|--------|---------|
| Health script FAIL | Container down, disk full, backend dead |
| LND always locked when you expect work | Restart without unlock |
| Channel low inbound (remote) | Receive capacity low — rebalance/Loop Out later, don’t close good channels |
| Channel low outbound (local) | Send capacity low |
| Zero active channels | Open/reconnect peers before payments |
| Repeated auth failed in backend logs | Wrong key or probing |
| Unexpected fee/payment log lines | Investigate; rotate keys if needed |
| loop getinfo failed | Loop/LND wiring — see [loop-autoloop.md](./loop-autoloop.md) |

### Loop Autoloop (Phase 2)

Liquidity automation is **infrastructure**, not part of payment agents.

**Overview:** [liquidity-automation.md](./liquidity-automation.md)
**Operator deep dive:** [loop-autoloop.md](./loop-autoloop.md)

1. Keep monitoring with `./check-aws-health.sh` (Phase 1 floors).
2. Wire Autoloop to the **agent** node (not demo `loopclient` / `lndclient`):

```bash
# On AWS — after Loop stack + agent LND are up
./wire-agent-loopd.sh
export LOOP_CLI='docker exec -i agent-loopd loop'
./configure-autoloop-regtest.sh --apply
# Enable only when ready on regtest:
# ./configure-autoloop-regtest.sh --apply --enable
```

3. Re-run `./wire-agent-loopd.sh` after cold starts; re-`--apply` (and `--enable` if desired) after loopd restarts if params reset.
4. Mainnet Autoloop is **out of scope** for this phase.

---

## Workflow

The current workflow is shown here. This is the test workflow on regtest.

Use **`<AWS_EIP>`** = current Elastic IP (see [Current environment](#current-environment-operator) above; today `3.90.159.146`).

- 1) On AWS: `./startup-aws.sh regtest <AWS_EIP>`
- 2) On AWS: Fund LND node. See below.
- 3) On Mac: `./startup-mac.sh regtest <AWS_EIP>`
- 4) On Mac: `./wait-mac-lnd.sh regtest`
- 5) On Mac: `./connect-mac-to-aws.sh <AWS_EIP> <pubkey-from-aws-getinfo>` See below.
- 6) On Mac: Verify peer connection Mac <-> AWS. See below.
- 7) On Mac: Open Lightning channel Mac <-> AWS. See below.
- 8) On Mac: `uv run python tests/test_aws_integration.py --backend-url http://<AWS_EIP>:8000`
- 9) On AWS: `./shutdown-aws.sh`
- 10) On Mac: `./shutdown-mac.sh`

### Optional diagnostics
Run these commands after each workflow step to determine if everything launched correctly.

- STEP #1. On AWS:

```bash
echo "=== Post-Startup Diagnostics (AWS) ==="

echo "Containers:"
docker ps

echo -e "Bitcoind Height:"
docker exec bitcoind bitcoin-cli -regtest -rpcuser=lightning -rpcpassword=lightning getblockcount

echo -e "LND Sync Status:"
docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "block_height|synced_to_chain|synced_to_graph|identity_pubkey"

echo -e "Backend API Balance:"
curl -s http://localhost:8000/balance | jq . 2>/dev/null || curl -s http://localhost:8000/balance || echo "API not responding yet"

echo -e "Recent LND Logs:"
docker logs --tail 20 agent-payment-decision-lnd | tail -15

echo -e "Command to start agent-payment-decision-lnd"
docker compose -f docker-compose.regtest.aws.yml up -d agent-payment-decision-lnd
```

- STEP #2. On AWS:

```bash
# Get new LND address
ADDR=$(docker exec agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest newaddress p2wkh | jq -r '.address')
echo "Funding address: $ADDR"

# Send 5 BTC from miner wallet
docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner sendtoaddress $ADDR 5

# Mine blocks to confirm
docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner generatetoaddress 6 $(docker exec bitcoind bitcoin-cli -regtest -rpcwallet=miner getnewaddress "")

# Check balance
curl -s http://localhost:8000/balance | jq .
```

- STEP #3. On Mac:

```bash
echo "=== Post-Startup Diagnostics (Mac) ==="

echo "1. Container Status:"
docker compose -f docker-compose.regtest.mac.yml ps

echo -e "Bitcoind Height (Mac):"
docker compose -f docker-compose.regtest.mac.yml exec bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getblockcount

echo -e "agent-bitcoin-lnd Status:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "identity_pubkey|block_height|synced_to_chain|synced_to_graph|uris"

echo -e "agent-bitcoin-1-lnd Status:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-1-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "identity_pubkey|block_height|synced_to_chain|synced_to_graph|uris"

echo -e "Test Connectivity to AWS bitcoind (from both agents):"
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  curl -s -X POST http://3.90.159.146:18443 -H "Content-Type: application/json" --data '{"jsonrpc":"1.0","id":"test","method":"getblockcount"}' || echo "Failed from agent-bitcoin-lnd"

docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-1-lnd \
  curl -s -X POST http://3.90.159.146:18443 -H "Content-Type: application/json" --data '{"jsonrpc":"1.0","id":"test","method":"getblockcount"}' || echo "Failed from agent-bitcoin-1-lnd"

echo -e "Recent Logs (agent-bitcoin-lnd):"
docker compose -f docker-compose.regtest.mac.yml logs --tail 20 agent-bitcoin-lnd | tail -10

echo -e "Show a live tail of the logs, updating in real time as Mac LND receives and processes blocks from AWS."
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd | grep -E "ZMQ|block|sync|new block|Filtering"
```

- STEP #4. On Mac:
-
```bash
echo "=== Mac Post-Startup Diagnostics ==="

echo "1. Containers:"
docker compose -f docker-compose.regtest.mac.yml ps

echo -e "Bitcoind Height (Mac):"
docker compose -f docker-compose.regtest.mac.yml exec -T bitcoind bitcoin-cli -regtest -rpcuser=rpcuser -rpcpassword=rpcpass getblockcount

echo -e "Mac LND Status:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "identity_pubkey|block_height|synced_to_chain|synced_to_graph"

echo -e "Connection to AWS LND:"
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers | grep -E "pub_key|address"

echo -e "Recent Mac LND Logs:"
docker compose -f docker-compose.regtest.mac.yml logs --tail 15 agent-bitcoin-lnd | tail -10
```

- STEP #5. It can take a fairly long time to sync the Lightning node with the Bitcoin blockchain. If you see "synced_to_chain: false", run these commands to advance the chain and force LND to catch up. This is not guaranteed to work. You may have to simply wait some time for the nodes to sync.

- Explanation for why mining more blocks on AWS helps the Mac LND sync faster:

- Your setup is:

  - AWS: Runs bitcoind (the Bitcoin blockchain) + agent-payment-decision-lnd
  - Mac: Runs only agent-bitcoin-lnd (connects to AWS bitcoind via RPC + ZMQ)

- When you mine blocks on AWS:

1) The AWS bitcoind adds new blocks to the blockchain.
2) The Mac LND is configured to listen to AWS bitcoind for new blocks (via ZMQ notifications on ports 28332/28333) and to query it via RPC.
3) When new blocks appear, the Mac LND gets notified and starts downloading and validating them.
4) This advances the Mac LND’s block_height and eventually flips synced_to_chain from false to true.

```bash
# On AWS:

# Mine more blocks
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress 200 $(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress "")

# On Mac:

# Restart Mac LND
docker compose -f docker-compose.regtest.mac.yml restart agent-bitcoin-lnd

sleep 15

# Unlock if needed
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest unlock

# Monitor
./wait-mac-lnd.sh regtest
```

- STEP #6. On Mac:

Use AWS agent-payment-decision-lnd pubkey.

```bash
docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest connect \
  <AWS_LND_PUBKEY>@<AWS_EIP>:9735
```

- STEP #7. On Mac:

```bash
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest listpeers
```

- STEP #8. On Mac:

Use AWS agent-payment-decision-lnd pubkey.

```bash
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
  --node_key 0258b1aefcaa9c03423647a1c17094f04616a4849696d1db7ec67943eae73ab0ec \
  --local_amt 1000000 \
  --push_amt 500000
```

- STEP #9. On AWS:

```bash
echo "=== Agent-Bitcoin Shutdown Diagnostics ==="

echo "→ Running containers:"
docker ps

echo "→ Agent networks:"
docker network ls | grep -E "agent|agent-net"

echo "→ Backend processes:"
ps aux | grep -E "uv run|backend/main.py" | grep -v grep

echo "→ Volumes (LND volume should remain):"
docker volume ls | grep agent-bitcoin

echo ""
echo "✅ If no containers or agent networks appear above, shutdown is clean."
echo "   (LND volume is intentionally kept for faster restarts)"
```

- STEP #10. On Mac:

```bash
echo "=== Mac Shutdown Diagnostics ==="

echo "→ Running containers:"
docker ps

echo "→ Agent networks:"
docker network ls | grep -E "agent|agent-lightning-net"

echo "→ Backend processes:"
ps aux | grep -E "uv run|backend/main.py" | grep -v grep

echo "→ Volumes (should keep LND and bitcoind data):"
docker volume ls | grep -E "agent-bitcoin|bitcoind"

echo ""
echo "✅ If no containers or agent networks appear above, shutdown is clean."
echo "   (Volumes are intentionally kept for faster restarts)"
```

---

## Publish to TestPyPi

- Update pyproject.toml as appropriate.

```bash
# Build and upload to TestPyPI
cd ~/agent-bitcoin
rm -rf dist/ build/ *.egg-info/
uv tool install twine
uv build
twine upload --repository testpypi dist/*
```

---

## AWS

### Instance type

- Currently using the AWS instance types:
t3.medium
i4i.xlarge

### SSH
Here is the command to ssh into a running AWS instance.

Note: the URL will change each time a new instance is started.

```bash
ssh -i ~/.ssh/aws/agent-bitcoin-key.pem ubuntu@3.90.159.146
```

### Start backend in tmux
```bash
tmux new-session -d -s backend "cd ~/agent-bitcoin && PYTHONPATH=. uv run python backend/main.py"
```

### Check if it's running
```bash
tmux ls
curl http://localhost:8000/balance
```

### docker-compose.regtest.yml

If you modify the file docker-compose.regtest.yml, immediately instantiate the changes by running these commands:

```bash
docker compose -f docker-compose.regtest.aws.yml down
docker compose -f docker-compose.regtest.aws.yml up -d
```

### AWS monitoring data

```bash
# 1. Current instance type and specs
echo "Instance type:"; curl -s http://169.254.169.254/latest/meta-data/instance-type

# 2. CPU usage
echo -e "\nCPU Usage:"; top -bn1 | head -n 20

# 3. Memory usage
echo -e "\nMemory Usage:"; free -h

# 4. Disk I/O (important for bitcoind + LND)
echo -e "\nDisk I/O:"; iostat -x 1 3 | tail -n 20

# 5. Current running processes
echo -e "\nTop processes:"; ps aux --sort=-%cpu | head -n 15
```

---

## Bitcoin wallet management
```bash
echo "→ Deleting ALL Bitcoin wallets (clean slate)..."

# Unload all wallets
docker exec bitcoind bitcoin-cli -regtest listwallets | \
  docker exec -i bitcoind xargs -I {} bitcoin-cli -regtest unloadwallet "{}" 2>/dev/null || true

# Delete the entire wallets directory (nuclear but safe on regtest)
docker exec bitcoind rm -rf /home/bitcoin/.bitcoin/regtest/wallets

# Recreate the empty wallets directory
docker exec bitcoind mkdir -p /home/bitcoin/.bitcoin/regtest/wallets

echo "✅ All wallets deleted. Fresh start ready."
```

---

## Lightning Labs Loop service

- We use Lightning Labs Loop for lightning channel management and funding.
- **Liquidity automation (Phases 1–3 overview):** **[liquidity-automation.md](./liquidity-automation.md)**
- **Autoloop / Phase 2 deep dive:** **[loop-autoloop.md](./loop-autoloop.md)**, `./wire-agent-loopd.sh`, `./configure-autoloop-regtest.sh`

- The Loop github repo is: https://github.com/lightninglabs/loop

- Install, configure and run Loop in regtest.

```bash
#!/bin/bash
set -e

echo "=== Setting up Loop on regtest (official environment) ==="

# 1. Install docker-compose if needed
echo "Installing docker-compose..."
sudo apt update
sudo apt install -y docker-compose

# 2. Clone Loop repo
echo "Cloning Loop repo..."
cd ~
git clone https://github.com/lightninglabs/loop.git || true
cd loop/regtest

# 3. Update docker-compose.yml to use working etcd image
echo "Updating etcd image..."
sed -i 's|bitnami/etcd:.*|quay.io/coreos/etcd:v3.5.18|' docker-compose.yml

# 4. Clean up old conflicting containers
echo "Cleaning up old containers..."
cd ~/agent-bitcoin || true
docker compose -f docker-compose.regtest.aws.yml down 2>/dev/null || true
docker rm -f $(docker ps -aq) 2>/dev/null || true
docker volume rm $(docker volume ls -q) 2>/dev/null || true

# 5. Start the official regtest environment
echo "Starting regtest environment..."
cd ~/loop/regtest
./regtest.sh start

echo "✅ Loop regtest setup complete!"
echo "Test with: loop --network=regtest getinfo"
```

---

## Lightning channels

Here are instructions for managing Lightning channels.

### Step 1: Fund the AWS node

- Run these commands on the AWS instance:

It may be necessary to run this first if using regtest:

```bash
# Set a fallback fee
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc settxfee 0.00001
```

```bash
# 1. Get a new address on the AWS payment-decision node
ADDR=$(docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest newaddress p2wkh | jq -r .address)
echo "AWS Address: $ADDR"

# 2. Send coins from bitcoind to the AWSpayment-decision node
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc sendtoaddress "$ADDR" 20

# 3. Mine blocks to confirm the funds
docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc generatetoaddress 6 $(docker exec bitcoind bitcoin-cli -regtest -rpcuser=btc -rpcpassword=btc getnewaddress)

# 4. Check balance on AWS
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest walletbalance
```

Summary
- AWS payment-decision-lnd now has 2,000,000,000 sats (20 BTC) confirmed.

### Step 2: Connect Mac to AWS

- Run this command on the Mac:

- Note: You will have to update the AWS instance IP address every time you launch a new instance

```bash
# Prefer: ./connect-mac-to-aws.sh 3.90.159.146 <pubkey-from-aws-getinfo>
docker exec agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest \
  connect <AWS_LND_PUBKEY>@3.90.159.146:9735
```

### Open Lightning channel from Mac to AWS
```bash
# Open a 5M sat channel (you can adjust the amount)
docker compose -f docker-compose.regtest.mac.yml exec -it agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest openchannel \
    --node_key 039f2162629469491bf27e39d5f679d601662953b2db437db24e08c91b5d71b6de \
    --local_amt 5000000 \
    --push_amt 2000000
```

### Open Channel Mac <--> AWS
```bash
# Get the identity pubkey of the AWS node
# Run this command on AWS node
docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo
```

```bash
# 1. Connect Mac node to AWS node
#    Run these commands on Mac
#    Note: change the pubkey based on the previous command
docker exec agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest \
  connect <AWS_LND_PUBKEY>@3.90.159.146:9735

# 2. Open channel from Mac to AWS
docker compose exec -T agent-bitcoin-lnd lncli --network=regtest openchannel \
  --node_key 022c3c33f5974b37861859de0417bf8f95fba55dae3677053c2aa6f9aaa2032b67 \
  --local_amt 5000000 \
  --push_amt 1000000
```

---

## Tests

### Test integration of frontend SDK with backend AWS API

File: tests/test_aws_integration.py

Run on mac:

```bash
# Basic usage (localhost)
uv run python tests/test_aws_integration.py

# With your AWS backend IP
uv run python tests/test_aws_integration.py --backend-url http://3.90.159.146:8000

# Custom amount
uv run python tests/test_aws_integration.py --backend-url http://3.90.159.146:8000 --amount 10000
```

---

## Logs

### Docker commands to follow log files
```bash
# On AWS:
docker compose -f docker-compose.regtest.aws.yml logs -f agent-payment-decision-lnd

# On Mac:
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd
```

---

## ZMQ (ZeroMQ) connands

- ZeroMQ is a high-performance, lightweight messaging library that allows different programs (in this case, bitcoind and LND) to communicate efficiently.

- In current setup, AWS bitcoind uses ZMQ to publish (send out) real-time notifications whenever
  - 1) a new block is mined (rawblock)
  - 2) a new transaction is seen (rawtx)

- ZMQ is the fast notification system that lets LND know immediately when new blocks arrive on the AWS node.

- Mac agent-bitcoin-lnd subscribes to those ZMQ feeds (on ports 28332 and 28333) so it can stay in sync with the Bitcoin blockchain without constantly polling.

Here are commands related to ZMQ.

```bash
# Check from Mac terminal whether agent-bitcoin-lnd is receiving ZMQ messages from AWS bitcoind. Look for lines like:
  # Started listening for bitcoind block notifications via ZMQ
  # New block epoch subscription
  # Received block or similar
docker compose -f docker-compose.regtest.mac.yml logs --tail 50 agent-bitcoin-lnd | grep -E "ZMQ|block|sync|new block"
```

- More detailed ZMQ status

```bash
# Check if LND is connected to ZMQ
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest getinfo | grep -E "block_height|synced_to_chain"

# Watch live ZMQ activity
docker compose -f docker-compose.regtest.mac.yml logs -f agent-bitcoin-lnd | grep -E "ZMQ|block|height"
```

- Verify ZMQ ports are open
  - If ports 28332 and 28333 are listening, ZMQ is configured.

```bash
docker compose -f docker-compose.regtest.mac.yml exec agent-bitcoin-lnd \
  ss -tlnp | grep -E "28332|28333"
```

---

## Terminal screen management

- Sometimes, the terminal is left in an unstable state.  These commands usually fix it.

| Command   | What it does                    | When to use                 |
|:----------|:--------------------------------|:----------------------------|
| stty echo | Turns typing visibility back on | When text is invisible      |
| stty sane | Best all around fix             | When output looks broken    |
| reset     | Full terminal reset             | When stty sane isn't enough |

---
