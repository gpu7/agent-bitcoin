# Setup Guide

Short pointers only. Full detail lives in the primary docs.

## Prerequisites

- Python 3.10+
- `uv` (recommended) or `pip`
- For regtest: Docker + Docker Compose; AWS and/or Mac as in the operator guide

## Install the SDK

See **[SDK.md — Installation](../SDK.md#installation)** (TestPyPI or source with `uv sync`).

## Quick start (library)

See **[SDK.md — Quick start](../SDK.md#quick-start)** and **[README.md](../README.md)**.

```python
from agent_bitcoin import create_client

client = create_client()
invoice = client.create_invoice(memo="Test", amount_sats=5000)
result = client.pay_invoice(invoice.payment_request)
```

This requires a working Lightning path (LND / backend). It does **not** take a `backend_url` argument on `create_client()` today.

## Full regtest environment (AWS + Mac)

See **[backend.md](./backend.md)** for:

- `startup-aws.sh` / `startup-mac.sh` / `wait-mac-lnd.sh`
- Funding, connect, channels, integration tests
- Shutdown and volume-preserving ops

## HTTP Backend API

When `backend/main.py` is running (port 8000), agents can use the JSON API documented in **[SDK.md — HTTP Backend API](../SDK.md#http-backend-api)**.
