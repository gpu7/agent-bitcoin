# L402 client pack (private 100-sat channel)

Turnkey **as far as Lightning allows**: Docker LND (Neutrino mainnet) on the **client** machine, one setup script, one smoke pay. We admit their host with a security-group `/32`. We do **not** run their wallet.

Scripts: [examples/client-pack/](../examples/client-pack/). Product context: [l402-external-agent.md](./l402-external-agent.md).

Lab HTTP: `http://3.90.159.146:8081`. AWS peer:

```text
0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967@3.90.159.146:9735
```

## What you will do (coordination is explicit)

| Who | Action |
|-----|--------|
| Client | `setup.sh` → send **only** `client-hello.json` (egress IP + LND pubkey) |
| Operator | Add that IP `/32` on **8081** and **9735**. Unlock AWS LND. **10009 stays closed.** |
| Client | Fund on-chain, optional `setup.sh --open-channel SATS` (**`--private`**) |
| Operator | Confirm channel active |
| Client | `smoke-l402.sh` (100-sat GET feerate) |
| Operator | Revoke = delete those `/32` rules |

This is not automatic. Allowlist, funding, and the private channel each need a human.

## Client machine

Needs: Docker, Python 3.12, this repo (or `pip install agent-bitcoin` plus `examples/l402_pay.py`).

Install **Docker Desktop** from [https://www.docker.com](https://www.docker.com).
On Ubuntu you can use Docker Engine: see [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
Confirm:

```bash
docker version
docker compose version
```

Install **Python 3.12** from [https://www.python.org](https://www.python.org) (or your OS package manager). Check:

```bash
python3.12 --version
```

You want Python 3.12.x. If that command is missing, try python3 --version. If that prints 3.10 or 3.11, still install 3.12; the pack is written for 3.12.On Ubuntu you can also use:

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv
python3.12 --version
```

That should print Python 3.12.x. If it does, you are done. Then use:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version    # now 3.12 inside the venv
```

If python3.12 --version is not found:

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3.12-dev
python3.12 --version
```

Get this repository (Git from your package manager if needed):

```bash
sudo apt install -y git
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
git pull origin main
```

Then run these commands

```bash
cd examples/client-pack
./setup.sh
docker exec -it l402-client-lnd lncli --lnddir=/home/lnd/.lnd --network=mainnet create
# Input a wallet password
# Save the cipher seed offline. Never send it to anyone.
```

Then run this command again:
```bash
./setup.sh
```

If the wallet is locked, unlock it:
```bash
docker exec -it l402-client-lnd lncli --lnddir=/home/lnd/.lnd --network=mainnet unlock
```

Then run this command again:
```bash
./setup.sh
```

This time, `setup.sh` will write the file `client-hello.json`. Send that file to us.


## Operator admit

After receiving the file `client-hello.json`, note the `egress_ip` and `identity_pubkey`.  On AWS get the security group ID associated with the running agent-bitcoin EC2 instance:

```bash
# run on AWS

# get security group ID
TOKEN=$(curl -sS -X PUT http://169.254.169.254/latest/api/token \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
MAC=$(curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/mac)
curl -sS -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/network/interfaces/macs/$MAC/security-group-ids

SG=security_group_id
IP=egress_ip

aws ec2 authorize-security-group-ingress \
  --group-id "$SG" \
  --region us-east-1 \
  --ip-permissions "[
    {\"IpProtocol\":\"tcp\",\"FromPort\":8081,\"ToPort\":8081,
     \"IpRanges\":[{\"CidrIp\":\"${IP}/32\",\"Description\":\"l402 client pack 8081\"}]},
    {\"IpProtocol\":\"tcp\",\"FromPort\":9735,\"ToPort\":9735,
     \"IpRanges\":[{\"CidrIp\":\"${IP}/32\",\"Description\":\"l402 client pack 9735\"}]}
  ]"

# verify
aws ec2 describe-security-groups --group-ids "$SG" \
  --query 'SecurityGroups[0].IpPermissions[?FromPort==`8081` || FromPort==`9735`]'
```

Do **not** open 8081 to `0.0.0.0/0`. Do **not** publish 10009.

## Fund Client Machine

See whether a channel exists.  Run on client machine:

```bash
docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet getinfo

docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet listpeers

docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet listchannels
```
Check Lightning wallet balance on client machine. Run:

 ```bash
docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet walletbalance
```

If confirmed_balance is 0, get a deposit address:

```bash
docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet newaddress p2wkh
```

Send mainnet BTC to that address from an exchange or wallet you control. 
Amount: channel size + miner fee (for example: 50,000 sats). 
Wait until walletbalance shows a confirmed balance (typically ca. 10 minutes but can vary somewhat).
After walletbalance shows a confirmed balance, open a private channel to AWS:
```bash
docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet connect \
  0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967@3.90.159.146:9735

docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet openchannel \
  --private \
  --node_key=0290ec8b1733192e5dcbc5d32f8fec5ae345ff777fc48dafed757c2d14781d4967 \
  --local_amt=50000
```
--local_amt must be less than confirmed balance minus fee. Adjust if walletbalance is smaller.

Wait for the private channel to be active:
```bash
docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet pendingchannels

docker exec l402-client-lnd \
  lncli --lnddir=/home/lnd/.lnd --network=mainnet listchannels
```
You want "pending_open_channels" is empty, "active": true, "private": true and local_balance enough for 100 sats + reserve.

Run smoke test on client machine:
```bash
export LND_NETWORK=mainnet
export LND_TRANSPORT=docker
export LND_CONTAINER=l402-client-lnd
export AGENT_BITCOIN_ALLOW_MAINNET=1
export AGENT_BITCOIN_ALLOW_AUTOPAY=1

./smoke-l402.sh
```


## What this is not

- A public URL or `0.0.0.0/0` on 8081
- Our Mac LND as their wallet
- Hosted wallet, NWC custody, or Autoloop
- Auto security-group changes from the client
- Sending `wallet.db` or seed to AWS
