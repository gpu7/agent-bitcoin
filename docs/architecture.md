# Architecture

Diagrams for engineers. Runtime and operator detail stays in [l402-aperture.md](./l402-aperture.md) and [backend.md](./backend.md).

## L402 deployment

```mermaid
flowchart TB
  Mac["Mac payer<br/>examples/l402_pay.py / L402Client"]
  Net["Internet"]

  subgraph sg["AWS security group"]
    direction TB
    subgraph ec2["AWS EC2"]
      direction TB
      Aperture["agent-l402-aperture :8081"]
      Origin["agent-l402-origin :8090<br/>private docker network"]
      LND["AWS LND :10009<br/>agent-payment-decision-lnd / -signet / -mainnet<br/>invoice.macaroon for Aperture<br/>readonly for origin path-hint"]
    end
  end

  Mac -->|"HTTP / L402"| Net
  Net -->|"TCP 8081 operator /32"| Aperture
  Aperture -->|"after pay"| Origin
  Aperture -->|"create invoice"| LND
  Origin -.->|"path-hint only"| LND
```

Public door is 8081 /32; LND is not world-open.

## L402 request sequence

Example paid path: `GET /paid/finance/mempool-feerate`. Same 402 → pay → retry for other paid GET/POST paths.

```mermaid
sequenceDiagram
  participant Agent as Agent
  participant Aperture as Aperture :8081
  participant Origin as Origin :8090
  participant LND as LND :10009
  participant Wallet as Payer wallet

  Agent->>Aperture: GET paid path
  Aperture->>LND: create invoice
  Aperture-->>Agent: 402 L402 challenge
  Agent->>Wallet: pay BOLT11
  Agent->>Aperture: retry L402 auth
  Aperture->>Origin: proxy after pay
  Origin-->>Aperture: JSON or file
  Aperture-->>Agent: 200
```

- Unpaid requests stop at 402.
- Finance/Nostr tools typically 100 sats; hello/PDF/PNG 1000.
- 8081 allowlist is separate from payment.
- Origin does not charge; Aperture is the cash register.

Two-agent swarm (who pays one GET): [examples/swarm_l402.md](../examples/swarm_l402.md) (live demo pays from the Mac).

## Wallets and chain backends

Mainnet names; signet/regtest are analogous ([l402-aperture.md](./l402-aperture.md) table).

Each host has its own **bitcoind** (blocks) and its own **LND wallet** (keys, on-chain sats, channel sats). bitcoind does not hold spend keys in this lab — LND `wallet.db` does.

In operator terms: the “Bitcoin wallet” is LND on-chain (`walletbalance` / `newaddress`). The “Lightning wallet” is the **same** LND’s channel balances (`listchannels`). Dual-node lab = **two** LND wallets, not four key stores.

![Two LND wallets](images/wallets-mac-aws.jpg)

*Two LND wallets; bitcoind is chain data; live L402 pays from Mac.*

### Wallet deployment

```mermaid
flowchart TB
  subgraph mac["Mac"]
    MacBTC["agent-bitcoin-bitcoind-mainnet<br/>blocks only"]
    MacLND["agent-bitcoin-lnd-mainnet<br/>LND wallet on-chain + LN"]
    Agent["Agent / swarm"]
    MacBTC --> MacLND
  end

  subgraph sg["AWS security group"]
    subgraph aws["AWS"]
      AwsBTC["agent-payment-decision-bitcoind-mainnet<br/>blocks only"]
      AwsLND["agent-payment-decision-lnd-mainnet<br/>LND wallet 10009 private"]
      Aperture["agent-l402-aperture :8081"]
      AwsBTC --> AwsLND
      Aperture -->|"create invoice"| AwsLND
    end
  end

  MacLND -->|"channel 9735"| AwsLND
  Agent -->|"HTTP L402 /32"| Aperture
  Agent -->|"pay BOLT11"| MacLND
```

Public door is 8081 /32; LND gRPC 10009 is not world-open.

### Live L402 across two wallets

```mermaid
sequenceDiagram
  participant Agent as Agent Mac
  participant Aperture as Aperture :8081
  participant AwsLND as AWS LND
  participant MacLND as Mac LND
  participant Origin as Origin :8090

  Agent->>Aperture: GET or POST paid URL
  Aperture->>AwsLND: addinvoice
  Aperture-->>Agent: 402 + BOLT11
  Agent->>MacLND: sendpayment
  MacLND->>AwsLND: HTLC on channel
  Agent->>Aperture: retry L402
  Aperture->>Origin: proxy after pay
  Origin-->>Agent: JSON
```

AWS LND paying that invoice is rejected (self-pay). Payer is Mac LND.
