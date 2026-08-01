# LND client transports

**Audience:** Operators and SDK users.
**Related:** [mainnet-pilot.md](./mainnet-pilot.md) · [signet.md](./signet.md) · [SDK.md](../SDK.md)

The SDK talks to LND through one of two transports, selected by env:

| `LND_TRANSPORT` | How it talks to LND | Default |
|-----------------|---------------------|---------|
| `docker` | `docker exec … lncli` into a local container | **yes (lab)** |
| `grpc` | gRPC + TLS cert + macaroon (via `lnd-grpc-client`) | production path |

```python
from agent_bitcoin import create_client
# or: from agent_bitcoin.lightning import create_lnd_client, LNDClient

client = create_client()  # uses LND_TRANSPORT from environment
```

---

## Docker transport (lab)

```bash
export LND_TRANSPORT=docker   # or omit — this is the default
export LND_NETWORK=signet     # or regtest
export LND_CONTAINER=agent-bitcoin-lnd-signet
export LND_DIR=/home/lnd/.lnd
```

Requires Docker on the same host as the container. Used by dual-node Mac/AWS lab scripts and `examples/signet_product_path.py`.

---

## gRPC transport (Phase 1 production path)

### Env

```bash
export LND_TRANSPORT=grpc
export LND_NETWORK=signet          # still required for policy/mainnet latch
export LND_GRPC_HOST=127.0.0.1
export LND_GRPC_PORT=30009         # host-mapped gRPC (Mac signet compose uses 30009)
export LND_TLS_CERT_PATH=/path/to/tls.cert
export LND_MACAROON_PATH=/path/to/admin.macaroon   # prefer restricted macaroon later
```

Aliases: `LND_CERT_PATH` accepted for the TLS cert.

**Do not** expose gRPC (`10009` / mapped host port) to `0.0.0.0/0`. Prefer localhost, private VPC, or SSH tunnel.

### Export cert + macaroon from a signet container (Mac example)

```bash
# Mac signet LND host port 30009 → container 10009
export MAC_LND=agent-bitcoin-lnd-signet
mkdir -p "$HOME/.lnd-export/signet-mac"
docker cp "$MAC_LND:/home/lnd/.lnd/tls.cert" "$HOME/.lnd-export/signet-mac/tls.cert"
docker cp "$MAC_LND:/home/lnd/.lnd/data/chain/bitcoin/signet/admin.macaroon" \
  "$HOME/.lnd-export/signet-mac/admin.macaroon"
chmod 600 "$HOME/.lnd-export/signet-mac/"*

export LND_TRANSPORT=grpc LND_NETWORK=signet
export LND_GRPC_HOST=127.0.0.1 LND_GRPC_PORT=30009
export LND_TLS_CERT_PATH="$HOME/.lnd-export/signet-mac/tls.cert"
export LND_MACAROON_PATH="$HOME/.lnd-export/signet-mac/admin.macaroon"

uv run python -c "
from agent_bitcoin.lightning import create_lnd_client
c = create_lnd_client()
print('transport', c.transport)
print(c.get_info().get('identity_pubkey'))
print(c.get_channel_balance())
"
```

### AWS signet (agent) example

```bash
export AWS_LND=agent-payment-decision-lnd-signet
# host map from docker-compose.signet.aws.yml: 20009 -> 10009
mkdir -p "$HOME/.lnd-export/signet-aws"
docker cp "$AWS_LND:/home/lnd/.lnd/tls.cert" "$HOME/.lnd-export/signet-aws/tls.cert"
docker cp "$AWS_LND:/home/lnd/.lnd/data/chain/bitcoin/signet/admin.macaroon" \
  "$HOME/.lnd-export/signet-aws/admin.macaroon"
chmod 600 "$HOME/.lnd-export/signet-aws/"*

export LND_TRANSPORT=grpc LND_NETWORK=signet
export LND_GRPC_HOST=127.0.0.1 LND_GRPC_PORT=20009
export LND_TLS_CERT_PATH="$HOME/.lnd-export/signet-aws/tls.cert"
export LND_MACAROON_PATH="$HOME/.lnd-export/signet-aws/admin.macaroon"
```

Wallet must be **unlocked** for most RPCs (same as lncli).

### Least privilege (later / Phase 2+)

For agent processes that only create invoices, bake an **invoice** macaroon instead of `admin.macaroon`. Paying requires a broader macaroon; keep pay credentials off untrusted agent hosts when possible.

---

## Backend

`backend/main.py` uses the same `LNDClient()` factory. Set `LND_TRANSPORT` (and grpc paths if needed) **before** starting uvicorn.

---

## Mainnet latch

`LND_NETWORK=mainnet` still requires `AGENT_BITCOIN_ALLOW_MAINNET=1`. Transport choice does not bypass that.
