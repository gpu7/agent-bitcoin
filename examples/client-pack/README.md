# L402 client pack

Neutrino mainnet LND on **your** machine. Pay our Aperture at 100 sats over a **private** channel.

Full steps (client + operator admit): **[docs/l402-client-pack.md](../../docs/l402-client-pack.md)**.
Ubuntu Python CLI: **[docs/l402-client-pack-script.md](../../docs/l402-client-pack-script.md)** (`python3.12 examples/client-pack/client_pack.py`).

```bash
cd examples/client-pack
./setup.sh                 # hello JSON → send IP+pubkey to operator
./setup.sh --open-channel 20000   # after you fund
./smoke-l402.sh            # GET mempool-feerate, 100 sats
```

Do not send the seed to AWS. Do not open 8081 yourself. Do not use our Mac LND.
