# Localhost infrastructure map

Read-only page for the operator Mac. It shows Bitcoin, the Lightning channel, the payer agent, the invoice agent, Nostr, Aperture, and the Merchant origin. Each node is up, down, locked, or unknown from a live probe.

The nodes are grouped into three boxes: **Chain** (Bitcoin network and Lightning channel), **Agents** (Payer agent, Invoice agent, and Nostr), and **Merchant** (Aperture and Merchant origin). Lines still connect the nodes. A failed probe stays down or unknown.

The process listens on **127.0.0.1** only. It does not bind `0.0.0.0`, and it does not use port 10009. It does not pay, create an invoice, open or close a channel, or unlock a wallet.

## Start

From the repo root, on the Mac:

```bash
uv run python -m agent_bitcoin.dashboard
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765) in Brave. `DASHBOARD_PORT` changes the port. `DASHBOARD_HOST` must stay `127.0.0.1`; any other value exits.

## What it probes

| Node | Probe |
|------|--------|
| Payer agent | Local Docker container `agent-bitcoin-lnd-mainnet` (regtest: `agent-bitcoin-lnd`, signet: `agent-bitcoin-lnd-signet`). `lncli getinfo` only. |
| Invoice agent | Local invoice container if this Mac is running it. Otherwise **unknown**. The AWS invoice node is not marked up from here. |
| Lightning channel | `lncli listchannels` on the payer after `getinfo` succeeds. Locked wallet stays **locked**. |
| Bitcoin network | Payer `synced_to_chain`, or a local bitcoind container. A failed probe stays failed. |
| Aperture | `GET $DASHBOARD_APERTURE_URL/health` and unpaid `GET .../paid/hello`. Default URL is `http://127.0.0.1:8081`. Healthy unpaid hello is HTTP 402. |
| Merchant origin | Docker container `agent-l402-origin` on this Mac. If it is only on AWS, the box stays **unknown**. |
| Nostr | TCP connect to `NOSTR_RELAYS` (default `relay.damus.io` and `nos.lol`) on port 443. No events are published. |

The command defaults to mainnet: `agent-bitcoin-lnd-mainnet`, `agent-payment-decision-lnd-mainnet`, `agent-payment-decision-bitcoind-mainnet`, `agent-l402-aperture`, and `agent-l402-origin`. It does not read `LND_NETWORK` and does not change the SDK regtest default. For the lab, add `--network regtest` or `--network signet`.

Set `DASHBOARD_APERTURE_URL` to the Aperture you can reach from this Mac, for example `http://3.90.159.146:8081`. Do not put that address in a public bind.

The page footer shows `git describe`. Probe errors are shortened. Macaroons, nsec values, seeds, and the unlock password are not returned.
