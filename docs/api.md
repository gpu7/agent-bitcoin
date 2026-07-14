# API Reference

The backend provides a REST API that AI agents can call.

Base URL: `http://localhost:8000` (or your AWS instance IP)

## Endpoints

### Create Invoice

**POST** `/invoices`

```json
{
  "memo": "Payment for service",
  "amount_sats": 5000
}
```

### Response

```json
{
  "payment_request": "lnbcrt...",
  "payment_hash": "...",
  "amount_sats": 5000
}
```

### Pay invoice

```json
{
  "payment_request": "lnbcrt..."
}
```

### Get balance

GET /balance

Returns Lightning + on-chain balances.



### Check invoice status

GET /invoices/paymenthash}
