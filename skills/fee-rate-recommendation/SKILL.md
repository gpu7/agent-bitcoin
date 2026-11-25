---
name: fee rate recommendation
description: Reports on-chain fee rates for 1, 3, and 6 block targets from an unlocked node when lncli is used.
summary: Read sat/vbyte estimates for three confirmation targets. Do not move funds.
version: 1.0.0
tags: bitcoin, fees, feerate
keywords: estimatesmartfee, estimatefee, sat/vbyte, agent-bitcoin
use_cases: Suggest an on-chain fee rate before any payment.
docs_url: https://github.com/gpu7/agent-bitcoin/blob/main/docs/agensi-deployment-test.md
---

# Fee rate recommendation

Read on-chain fee rates. Do not move funds and do not change channel state.

Do not sign in to Agensi from this skill. Regtest is the default. Set `AGENT_BITCOIN_ALLOW_MAINNET=1` only when the user has asked for a mainnet read.

## Check

The SDK has no fee-rate helper. Confirmation targets use bitcoin-cli. The regtest container is `bitcoind`:

```bash
docker exec bitcoind bitcoin-cli -regtest estimatesmartfee 1
docker exec bitcoind bitcoin-cli -regtest estimatesmartfee 3
docker exec bitcoind bitcoin-cli -regtest estimatesmartfee 6
```

`feerate` is BTC per kvB. Multiply by 100000 and report sat/vbyte. If the result has `errors` or no `feerate`, report that target as unavailable. Do not invent a number.

`estimatesmartfee` does not need an unlocked LND wallet. `lncli estimatefee` estimates one transaction and is not this confirmation-target table. If `estimatefee` fails with `wallet locked`, stop and say the wallet is locked. Do not pass an address or an amount to that call.

When all three rates are present, the 6-block rate is the default suggestion. Name the 1-block rate only when the user asked for the next block. The 3-block rate is the middle target.

## What to keep private

Do not print wallet secrets, macaroons, or preimages.
