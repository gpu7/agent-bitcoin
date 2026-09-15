# Ubuntu: `client_pack.py` trial

For an engineer on **Ubuntu** using the Python driver. The bash pack is unchanged: [l402-client-pack.md](./l402-client-pack.md).

Lab HTTP: `http://3.90.159.146:8081`. Your LND is container **`l402-client-lnd`**. We do not run your wallet.

## Docker + Python 3.12 + clone

Install Docker yourself (this script will **not** `sudo apt install docker`). Python 3.12:

```bash
python3.12 --version
# if missing: sudo apt install -y python3.12 python3.12-venv
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
git pull origin main
```

Optional venv:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Commands (this order)

```bash
python3.12 examples/client-pack/client_pack.py doctor
python3.12 examples/client-pack/client_pack.py up
python3.12 examples/client-pack/client_pack.py wallet
python3.12 examples/client-pack/client_pack.py hello
```

`hello` writes `examples/client-pack/client-hello.json` (egress IP + pubkey only). **Send that file to the operator.** `all` runs the four commands above, then **stops** — fund / open / smoke stay separate.

The operator still adds your `/32` on **8081** and **9735**. That procedure is in [l402-client-pack.md](./l402-client-pack.md) **Operator admit**. Do not run AWS APIs from the client box.

After they admit you and Neutrino is synced:

```bash
python3.12 examples/client-pack/client_pack.py status
python3.12 examples/client-pack/client_pack.py address
# fund ≥ ~50,000 sats (not 1000); wait for confirm
python3.12 examples/client-pack/client_pack.py open --sats 50000
python3.12 examples/client-pack/client_pack.py smoke
```

`open` is a **private** channel to `0290ec8b…@3.90.159.146:9735`. `smoke` is `GET /paid/finance/mempool-feerate` at 100 sats via `examples/l402_pay.py` with `LND_CONTAINER=l402-client-lnd` and the mainnet latches.

## What this script will not do

- `sudo` install Docker
- Open 8081 to `0.0.0.0/0` or publish 10009
- Put the seed in `client-hello.json`, git, or logs
- POST hello to us, or call AWS APIs
- Use our Mac LND or pay Aperture from AWS LND (self-pay)

Bash equivalent: [l402-client-pack.md](./l402-client-pack.md) (`setup.sh` / `smoke-l402.sh`).
