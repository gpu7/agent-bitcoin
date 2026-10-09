# Localhost infrastructure map

Read-only page for the operator Mac. It shows Bitcoin, the Lightning channel, the payer agent, the invoice agent, Nostr, Aperture, and the Merchant origin. Each node is up, down, locked, or unknown from a live probe.

The nodes are grouped into three boxes: **Chain** (Bitcoin network and Lightning channel), **Agents** (Payer agent, Invoice agent, and Nostr), and **Merchant** (Aperture and Merchant origin). The Aperture card shows health and the unpaid challenge separately. Lines still connect the nodes. A failed probe stays down or unknown.

The animation above the map is a picture of an agent-to-agent payment, not a live channel. Agent 1 and Agent 2 are labeled `npub1…` plus the last four characters of the public id, or `agent npub` when that id is missing. Agent 1 reads `.nostr-poc-mainnet/alice.pub.json` on this Mac. Agent 2 reads `.nostr-poc-mainnet/bob.pub.json` on this Mac. `DASHBOARD_AGENT1_NPUB` and `DASHBOARD_AGENT2_NPUB` override those files. Regtest and signet key directories are not used. For this lab the short forms are `npub1…68s8` and `npub1…sp9f`.

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
| Invoice agent | AWS `agent-payment-decision-lnd-mainnet` (regtest: `agent-payment-decision-lnd`, signet: `agent-payment-decision-lnd-signet`). `lncli getinfo` only, over SSH. If AWS cannot be reached, **unknown**. The Mac payer does not mark this box up. |
| Lightning channel | `lncli listchannels` on the payer after `getinfo` succeeds. Locked wallet stays **locked**. |
| Bitcoin network | Payer `synced_to_chain`, or a local bitcoind container. A failed probe stays failed. |
| Aperture | Health and the unpaid challenge are separate. `GET .../health` HTTP 200 is **up**. A missing `402` from `GET .../paid/hello` stays a failed challenge and does not mark health down. Default URL is `http://127.0.0.1:8081`. |
| Merchant origin | **up** only when Aperture `/health` returns 200, because the origin answered through the gateway. If Aperture cannot be reached, **unknown**. `agent-l402-origin` is not expected on this Mac. |
| Nostr | TCP connect to `NOSTR_RELAYS` (default `relay.damus.io` and `nos.lol`) on port 443. No events are published. |

The command defaults to mainnet. The payer container on this Mac is `agent-bitcoin-lnd-mainnet`. The invoice probe is AWS `agent-payment-decision-lnd-mainnet`. It does not read `LND_NETWORK` and does not change the SDK regtest default. For the lab, add `--network regtest` or `--network signet`.

Set `DASHBOARD_APERTURE_URL` to the Aperture you can reach from this Mac, for example `http://3.90.159.146:8081`. Do not put that address in a public bind.

The invoice probe uses the operator SSH path: `ubuntu` at `DASHBOARD_AWS_HOST`, or the host in `DASHBOARD_APERTURE_URL` when that host is not loopback, otherwise `3.90.159.146`. The key is `~/.ssh/aws/agent-bitcoin-key.pem`. The remote command is `docker exec` plus `lncli getinfo` in the AWS invoice container. It does not open port 10009. If that SSH path cannot be reached, the invoice box stays **unknown**.

The header shows the nearest git release tag, not the exact commit. If the repo has no tags, it shows a short commit hash. Probe errors are shortened. Macaroons, nsec values, seeds, and the unlock password are not returned.
