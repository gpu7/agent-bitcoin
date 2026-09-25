# AWS operator runbook

Audience: an operator who already has an AWS account and this repo. This is not a tutorial that launches a mainnet node with shared keys.

Diagram: [architecture.md](./architecture.md). Paid routes and YAML: [l402-aperture.md](./l402-aperture.md). Mainnet design notes: [mainnet-infra.md](./mainnet-infra.md). Optional HTTP API: [backend.md](./backend.md).

Use placeholders. Do not paste account IDs, AMI IDs, instance IDs, seeds, macaroons, or wallet passwords into git.

| Placeholder | Meaning |
|---|---|
| `<AWS_PUBLIC_IP>` | This box's public IPv4 (EIP if you attached one) |
| `<AWS_REGION>` | Region of the instance |
| `<SG_ID>` | Security group ID |
| `<KEY_NAME>` | SSH key pair name |
| `<INSTANCE_NAME>` | Name tag you chose |
| `<LND_UNLOCK_PASSWORD>` | Wallet unlock password. Never commit it |

## 1. What runs on AWS

Per network, the invoice side:

| Piece | Name | Where it listens |
|---|---|---|
| Invoice LND | `agent-payment-decision-lnd` (regtest), `agent-payment-decision-lnd-signet`, or `agent-payment-decision-lnd-mainnet` | Peer port below. gRPC stays off the security group |
| Chain backend | regtest/mainnet bitcoind in the AWS compose file; signet uses Neutrino | Not a public catalog |
| Aperture | `agent-l402-aperture` | Host **8081** |
| Origin | `agent-l402-origin` | `agent-l402-origin:8090` on the Docker network only. No host port |
| Optional backend | FastAPI from [backend.md](./backend.md) | Host **8000** if you start it |

`./startup-l402-aws.sh` does **not** start LND or the FastAPI backend. Start the invoice stack first.

The payer LND is **not** this box. It is the Mac node or a client-pack node. Paying an invoice from the same wallet that created it returns `self-payments not allowed`.

## 2. Ports and the security group

| Port | Why | Who |
|---|---|---|
| 22 | SSH | Operator `/32` |
| 8081 | Aperture L402 | Operator or an admitted client `/32` |
| 9735 | LND peer (regtest and mainnet) | Mac or client node that has a channel |
| 19735 | LND peer (signet host port; container still 9735) | Same, signet only |
| 10009 | LND gRPC (regtest maps it on the host) | Do **not** add it to the security group |
| 20009 | Signet host port for container gRPC 10009 | Do **not** add it to the security group |
| 8000 | Optional FastAPI backend | Operator `/32` only if you use it |

`./update-aws-sg-my-ip.sh` is additive for the operator IP. Default ports include 22, 8000, 8081, 9735, and 19735. It refuses a `PORTS` list that contains **10009**. It does not open `0.0.0.0/0`.

Never recommend `0.0.0.0/0` on **8081** or **10009**.

Only one L402 stack can bind **8081**. Stop the other network's Aperture before switching.

## 3. One-time box

Ubuntu-class AMI in `<AWS_REGION>`. Attach an EIP if you want `<AWS_PUBLIC_IP>` to survive stop/start. Name the instance `<INSTANCE_NAME>`. SSH with `<KEY_NAME>`. Security group `<SG_ID>` as in the table above.

On the instance:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker "$USER"
# log out and back in so the docker group applies

git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
git pull
```

Do not copy an AMI ID or account number into this repo.

Spot vs on-demand: a spot interruption stops the instance. LND comes back **locked**. Unlock again with `<LND_UNLOCK_PASSWORD>`. On-demand stop/start does the same to the wallet.

## 4. Start and stop

Invoice LND and chain first, then Aperture.

```bash
# Regtest. Second arg is the public IP the node advertises.
./startup-aws.sh regtest <AWS_PUBLIC_IP>

# Signet (Neutrino). No local bitcoind.
./startup-signet-aws.sh <AWS_PUBLIC_IP>

# Mainnet bitcoind + invoice LND. Set RPC user/password in the environment
# first (see docs/mainnet-infra.md). Do not put those values in git.
./startup-mainnet-aws.sh <AWS_PUBLIC_IP>
```

Then the gateway (default network is regtest):

```bash
./startup-l402-aws.sh mainnet
# or: ./startup-l402-aws.sh
# or: ./startup-l402-aws.sh signet
```

That script checks the Docker network and the invoice LND container, then runs `docker compose up -d --build` **without** `--remove-orphans`.

Do **not** add Compose `--remove-orphans` to the L402 command. Invoice LND and bitcoind belong to another compose file, so Docker treats them as orphans and can stop them. `./startup-aws.sh` uses `--remove-orphans` only when it stops its own regtest file.

Stop Aperture without deleting volumes:

```bash
./shutdown-l402-aws.sh mainnet
```

Stop the invoice stack with the matching script: `./shutdown-aws.sh`, `./shutdown-signet-aws.sh`, or `./shutdown-mainnet-aws.sh`. Those keep volumes. Do not `docker compose down --volumes` unless you intend to wipe LND.

## 5. After start

If `lncli getinfo` says the wallet is locked:

```bash
# Regtest
docker exec -it agent-payment-decision-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=regtest unlock

# Signet
docker exec -it agent-payment-decision-lnd-signet \
  lncli --lnddir=/home/lnd/.lnd --network=signet unlock

# Mainnet
docker exec -it agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock
```

Type `<LND_UNLOCK_PASSWORD>` at the prompt. Do not put it on the command line in a way that lands in shell history you commit.

On the instance:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8081/health
# 200

curl -sSI http://127.0.0.1:8081/paid/hello | head -n 1
# HTTP/1.1 402 Payment Required
```

`./check-aws-health.sh` is the **regtest backend** check (`http://127.0.0.1:8000` and container `agent-payment-decision-lnd`). It does not unlock LND and it does not call Aperture. Use the curls above for 8081.

## 6. After git pull

`./startup-l402-aws.sh <network>` rebuilds the origin image and recreates those containers. Aperture is in the same compose file, so it is recreated with origin. Invoice LND is not in that file and should keep running if you did not pass `--remove-orphans`.

Re-check 402 as in section 5.

If the channel's `active` field is false, reconnect from the **payer** node. Read the invoice node's pubkey at runtime (`lncli getinfo`). Do not treat a pubkey copied from an old note as the product key.

```bash
# Payer shell. Signet uses port 19735, not 9735.
lncli connect <pubkey-from-getinfo>@<AWS_PUBLIC_IP>:9735
```

## 7. Day-2

| Symptom | Likely cause |
|---|---|
| `getinfo` says wallet locked after reboot or spot stop | Unlock with `<LND_UNLOCK_PASSWORD>` |
| Channel `active: false` | Peer down, wrong port, or SG missing 9735/19735. Reconnect as in section 6 |
| Paid path returns 500 | Invoice LND is down or locked. Aperture cannot get a challenge invoice |
| `curl` to 8081 times out from your laptop | Security group or wrong `<AWS_PUBLIC_IP>`. On the box, 127.0.0.1:8081 should still answer |
| Two networks both want 8081 | Stop the other `./shutdown-l402-aws.sh <network>` first |

Backups: [lnd-backup-restore.md](./lnd-backup-restore.md). Closing a channel moves funds on-chain: [ln-channel-close.md](./ln-channel-close.md). Do not close a channel unless you mean to.

AMI snapshot: stop LND (and bitcoind) before a snapshot if you need a consistent `wallet.db`. A snapshot of a running node can tear that file. This repo does not store snapshot IDs or account IDs.

## 8. What this box is not

- Not a public Merchant catalog. 8081 stays an allowlist of `/32`s.
- Not the Mac or client-pack payer.
- Not an instruction to turn Autoloop on. Leave it off unless a separate regtest procedure says otherwise.
