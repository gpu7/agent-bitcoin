# Setup Guide

## Prerequisites

- Python 3.10+
- Docker + Docker Compose
- `uv` (recommended) or `pip`
- AWS account (for backend) or local machine for testing

## Installation

### From TestPyPI

```bash
pip install -i https://test.pypi.org/simple/ agent-bitcoin==0.2.0
```

### From source
```bash
git clone https://github.com/gpu7/agent-bitcoin.git
cd agent-bitcoin
uv sync
```

## Quick start
```bash
from agent_bitcoin import create_client

client = create_client(backend_url="http://your-aws-ip:8000")

invoice = client.create_invoice(memo="Test", amount_sats=5000)
result = client.pay_invoice(invoice.payment_request)
```

## Full Environment Setup (Regtest)

1)  AWS backend
```bash
# On AWS instance
./startup-aws.sh
```

2) Mac counterparty
```bash
# On Mac
./startup-mac.sh
```

3) Connect & open channel
See Workflow (./workflow.md) for detailed steps.
