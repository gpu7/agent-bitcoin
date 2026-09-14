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

Install **Docker Desktop** (or Docker Engine + Compose) from [https://www.docker.com](https://www.docker.com).
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
```

```bash
cd examples/client-pack
docker compose up -d          # or ./setup.sh does this
./setup.sh
# If no wallet yet: docker exec -it l402-client-lnd lncli --network=mainnet create
# Save the seed offline. Never send it to us or AWS. Re-run ./setup.sh
```

`setup.sh` writes `client-hello.json` (`egress_ip`, `identity_pubkey`). Send that file to the operator. Neutrino first sync can take a while; peers in compose can go stale.

Optional private channel (after confirmed coins, and after 9735 is allowlisted):

```bash
./setup.sh --open-channel 20000
```

Smoke (real sats; mainnet latches):

```bash
./smoke-l402.sh
```

That uses container **`l402-client-lnd`**, not our Mac `agent-bitcoin-lnd-mainnet`, and not AWS `agent-payment-decision-lnd-mainnet` (self-pay).

## Operator admit

When you have their `egress_ip` from hello JSON:

```bash
# On an operator machine with aws CLI — their IP, not yours
MY_IP=<client-egress-ip> PORTS="8081 9735" ./update-aws-sg-my-ip.sh --dry-run
# then without --dry-run if the CIDRs look right
```

Do **not** run that script from the client box (no auto-SG). Do **not** open 8081 to `0.0.0.0/0`. Do **not** publish 10009.

Unlock **AWS** LND (`agent-payment-decision-lnd-mainnet`). `listchannels` / `listinvoices` as usual. Revoke access by deleting their `/32` on 8081 and 9735.

## What this is not

- A public URL or `0.0.0.0/0` on 8081
- Our Mac LND as their wallet
- Hosted wallet, NWC custody, or Autoloop
- Auto security-group changes from the client
- Sending `wallet.db` or seed to AWS
