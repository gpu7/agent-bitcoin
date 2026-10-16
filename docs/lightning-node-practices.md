# Lightning node practices

Audience: the operator of this lab's AWS invoice node and Mac payer. This page records nine general practices. It does not change the node.

Related: [aws-operator.md](./aws-operator.md) · [lnd-backup-restore.md](./lnd-backup-restore.md)

For each practice: what the lab already does, then what you still do by hand. 2FA, SSH key custody, OS updates, and a watchtower stay operator work. This page does not enable them.

## 1. Cloud uptime

**Lab:** The invoice node is the AWS box. The runbook Elastic IP is `3.90.159.146`. Containers restart with the Docker policy. A stop, or a spot interruption, brings LND back locked.

**Operator:** Keep that instance running. After a stop, unlock the wallet. Prefer on-demand if a spot stop would lock the node at a bad time.

## 2. Control-panel 2FA

**Lab:** This repo does not configure the AWS account.

**Operator:** Turn on multi-factor authentication for the AWS console by hand.

## 3. SSH keys

**Lab:** SSH uses the named key pair. The dashboard probe uses `~/.ssh/aws/agent-bitcoin-key.pem`. Port 22 stays an operator `/32` on the security group.

**Operator:** Keep that private key private. Do not share the `.pem`.

## 4. Essential ports

**Lab:** 10009 is not public. 9735 and 8081 stay on the operator security group. `./update-aws-sg-my-ip.sh` refuses a `PORTS` list that contains 10009. It does not open `0.0.0.0/0`. Signet's host gRPC port 20009 is also left off the security group. The Mac payer publishes gRPC on `127.0.0.1` only.

**Operator:** Leave 10009 and 20009 off the security group. Keep 9735 and 8081 on the operator allowlist. This page does not change the security group.

## 5. Clean OS and containers

**Lab:** The box is Ubuntu with Docker. LND is the pinned image in the compose files. The stacks do not add extra public services.

**Operator:** Apply OS updates by hand. Do not add unused containers on the invoice host.

## 6. Limited macaroons

**Lab:** The dashboard is read-only and does not hold an admin macaroon. It binds to `127.0.0.1` and reads AWS with SSH `lncli getinfo`. The L402 origin uses a readonly macaroon limited to QueryRoutes and DecodePayReq. Aperture uses `invoice.macaroon`.

**Operator:** Do not copy `admin.macaroon` onto the dashboard host or into git. This page does not bake a macaroon.

## 7. Test an upgrade first

**Lab:** LND upgrades are tested elsewhere first. The current pin is `v0.18.5-beta` (`lightninglabs/lnd:v0.18.5-beta` on the AWS invoice node and the Mac payer).

**Operator:** Try a newer LND tag on another machine before changing that pin. This page does not move the pin.

## 8. Static channel backup

**Lab:** `./export-lnd-backup.sh` copies a backup under `~/lnd-backups/` when you set `LND_CONTAINER` and `LND_NETWORK`. `./verify-lnd-backup.sh` checks that directory. Git ignores `**/channel.backup`, `**/channel-all.backup`, and `lnd-backups/`. The restore story is [lnd-backup-restore.md](./lnd-backup-restore.md).

**Operator:** Export again after a channel open or close. That is when the file changes. You do not need a new file on an idle day with no channel change. The file is sensitive. Move it off the repo tree and off the instance. Do not commit it.

An SCB restores funds by force-closing channels. It does not restore the channels themselves. Restoring from it force-closes channels.

The wallet must be unlocked. If it is locked, `lncli` fails and no file is written.

On the AWS host, invoice node:

```bash
docker exec agent-payment-decision-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet \
  exportchanbackup --all --output_file /tmp/channel.backup
docker cp agent-payment-decision-lnd-mainnet:/tmp/channel.backup ./channel.backup
```

On the Mac, payer:

```bash
docker exec agent-bitcoin-lnd-mainnet \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet \
  exportchanbackup --all --output_file /tmp/channel.backup
docker cp agent-bitcoin-lnd-mainnet:/tmp/channel.backup ./channel.backup
```

`./channel.backup` is the copy in the current directory. Move it out of the git checkout. The same filename is gitignored if it is left behind.

`./export-lnd-backup.sh` is the other export. It writes a timestamped directory under `~/lnd-backups/` instead of `./channel.backup`.

## 9. Watchtower

**Lab:** A watchtower is optional and not enabled. No watchtower service is in the compose files.

**Operator:** Leave it off unless you choose to run one yourself. This page does not enable a watchtower.
