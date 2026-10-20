#!/bin/bash
# Register all /paid/finance endpoints on 402index with category bitcoin

set -euo pipefail

register() {
  local url="$1"
  local name="$2"
  local method="$3"
  local description="$4"

  echo "Registering $name ..."
  curl -sS -X POST https://402index.io/api/v1/register \
    -H 'Content-Type: application/json' \
    -d "{
      \"url\": \"$url\",
      \"name\": \"$name\",
      \"protocol\": \"L402\",
      \"description\": \"$description\",
      \"provider\": \"agent-bitcoin\",
      \"price_sats\": 100,
      \"category\": \"bitcoin\",
      \"http_method\": \"$method\"
    }"
  echo
  echo "---"
}

# Bitcoin suite (GET)
register \
  "https://agent-bitcoin.net/paid/finance/btc-usd" \
  "agent-bitcoin: btc-usd" \
  "GET" \
  "Bitcoin price in USD. Current BTC-USD rate and sats per USD from a public source. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/mempool-feerate" \
  "agent-bitcoin: mempool-feerate" \
  "GET" \
  "Bitcoin mempool fee rates. Sat/vB bands for fast, medium, and slow confirmation. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/mempool-backlog" \
  "agent-bitcoin: mempool-backlog" \
  "GET" \
  "Bitcoin mempool backlog. Transaction count, virtual size, and total fee. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/fee-for-vsize" \
  "agent-bitcoin: fee-for-vsize" \
  "GET" \
  "Fee in sats for a given virtual size. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/confirm-target" \
  "agent-bitcoin: confirm-target" \
  "GET" \
  "Map a confirmation wait time or band to sat/vB. Lightning L402."

# Lightning suite (POST)
register \
  "https://agent-bitcoin.net/paid/finance/ln-invoice-decode" \
  "agent-bitcoin: ln-invoice-decode" \
  "POST" \
  "Parse a Lightning BOLT11 invoice. Returns amount, expiry, and payee. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/ln-invoice-preflight" \
  "agent-bitcoin: ln-invoice-preflight" \
  "POST" \
  "Check whether a Lightning invoice is safe to pay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/ln-path-fee-hint" \
  "agent-bitcoin: ln-path-fee-hint" \
  "POST" \
  "First-path fee hint from the operator LND. Lightning L402."

echo "Done."
