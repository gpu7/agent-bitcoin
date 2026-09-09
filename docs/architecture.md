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
