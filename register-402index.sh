#!/bin/bash
# Register existing paid endpoints on 402index.
# Bitcoin suite stays bitcoin. Lightning is lightning. Nostr is nostr.
# Address check is verification. Challenge inspect is security.

set -euo pipefail

register() {
  local url="$1"
  local name="$2"
  local method="$3"
  local category="$4"
  local description="$5"

  echo "Registering $name ($category) ..."
  curl -sS -X POST https://402index.io/api/v1/register \
    -H 'Content-Type: application/json' \
    -d "{
      \"url\": \"$url\",
      \"name\": \"$name\",
      \"protocol\": \"L402\",
      \"description\": \"$description\",
      \"provider\": \"agent-bitcoin\",
      \"price_sats\": 100,
      \"category\": \"$category\",
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
  "bitcoin" \
  "Bitcoin price in USD. Current BTC-USD rate and sats per USD from a public source. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/mempool-feerate" \
  "agent-bitcoin: mempool-feerate" \
  "GET" \
  "bitcoin" \
  "Bitcoin mempool fee rates. Sat/vB bands for fast, medium, and slow confirmation. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/mempool-backlog" \
  "agent-bitcoin: mempool-backlog" \
  "GET" \
  "bitcoin" \
  "Bitcoin mempool backlog. Transaction count, virtual size, and total fee. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/fee-for-vsize" \
  "agent-bitcoin: fee-for-vsize" \
  "GET" \
  "bitcoin" \
  "Fee in sats for a given virtual size. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/confirm-target" \
  "agent-bitcoin: confirm-target" \
  "GET" \
  "bitcoin" \
  "Map a confirmation wait time or band to sat/vB. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-fee-estimate" \
  "agent-bitcoin: btc-fee-estimate" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core estimatesmartfee for 1, 3, and 6 blocks, in sats per vbyte. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-chain-status" \
  "agent-bitcoin: btc-chain-status" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core chain height, sync progress, and prune state from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-network-info" \
  "agent-bitcoin: btc-network-info" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core version, protocol, and connection counts from the operator bitcoind. Read-only. Lightning L402."

# Lightning suite (POST)
register \
  "https://agent-bitcoin.net/paid/finance/ln-invoice-decode" \
  "agent-bitcoin: ln-invoice-decode" \
  "POST" \
  "lightning" \
  "Parse a Lightning BOLT11 invoice. Returns amount, expiry, and payee. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/ln-invoice-preflight" \
  "agent-bitcoin: ln-invoice-preflight" \
  "POST" \
  "lightning" \
  "Check whether a Lightning invoice is safe to pay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/finance/ln-path-fee-hint" \
  "agent-bitcoin: ln-path-fee-hint" \
  "POST" \
  "lightning" \
  "First-path fee hint from the operator LND. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-channel-stats" \
  "agent-bitcoin: ln-channel-stats" \
  "GET" \
  "lightning" \
  "Lightning channel counts and balances from the operator LND. Read-only. Lightning L402."

# Address check (POST). Local only. No LND.
register \
  "https://agent-bitcoin.net/paid/finance/btc-address-validate" \
  "agent-bitcoin: btc-address-validate" \
  "POST" \
  "verification" \
  "Check a Bitcoin address. Returns network and type, or a short reason if invalid. Lightning L402."

# Challenge inspect (POST). Fetches one https URL. Does not pay.
register \
  "https://agent-bitcoin.net/paid/security/l402-challenge-inspect" \
  "agent-bitcoin: l402-challenge-inspect" \
  "POST" \
  "security" \
  "Inspect a remote L402 challenge. Returns price, expiry, and payee. Does not pay. Lightning L402."

# Nostr suite (POST). Existing routes. No relay.
register \
  "https://agent-bitcoin.net/paid/nostr/event-verify" \
  "agent-bitcoin: event-verify" \
  "POST" \
  "nostr" \
  "Check a Nostr event id and signature locally. No relay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/nostr/npub-decode" \
  "agent-bitcoin: npub-decode" \
  "POST" \
  "nostr" \
  "Decode a Nostr npub, note, nprofile, or nevent to hex. Rejects nsec. Lightning L402."

echo "Done."
