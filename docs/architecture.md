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
