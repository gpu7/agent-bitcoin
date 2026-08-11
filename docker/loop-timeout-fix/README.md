# Loop + LND `timeout_seconds` fix

## Problem

On **LND 0.18.x**, `routerrpc.SendPaymentV2` rejects payments with:

```text
timeout_seconds must be specified
```

Lightning Loop’s L402 auth path pays the challenge invoice via `lndclient.PayInvoice`, which builds a `SendPaymentRequest` **without** `TimeoutSeconds`. Result:

- `loop out` fails during L402 auth
- `l402.token.pending` appears with zero preimage
- no payment appears in `listpayments`
- bolt11 is **not** logged (so manual pay is hard)

## Fix

Rebuild `loop` / `loopd` with a one-line `lndclient` change: set `TimeoutSeconds: 60` on that `SendPaymentRequest`.

## Build

From repo root (needs Docker + network to GitHub):

```bash
docker build -t agent-bitcoin/loop:v0.34.0-beta-timeoutfix \
  -f docker/loop-timeout-fix/Dockerfile \
  docker/loop-timeout-fix
```

## Deploy (mainnet AWS)

```bash
# clear stuck unpaid L402
docker exec agent-loopd-mainnet rm -f /root/.loop/mainnet/l402.token.pending 2>/dev/null || true

export LOOPD_IMAGE=agent-bitcoin/loop:v0.34.0-beta-timeoutfix
./wire-loopd.sh mainnet --recreate

export LOOP_CLI='docker exec -i agent-loopd-mainnet loop'
$LOOP_CLI --network=mainnet getinfo
$LOOP_CLI --network=mainnet listauth   # expect []

# LND must stay unlocked; channel active
$LOOP_CLI --network=mainnet out \
  --channel=<your_chan_id> \
  --amt=250000 \
  --payment_timeout=1h
```

Volume `agent-loopd-mainnet-data` is preserved across `--recreate`.
