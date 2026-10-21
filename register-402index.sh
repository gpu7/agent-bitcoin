#!/bin/bash
# Register paid endpoints on 402index.
# Usage: ./register-402index.sh [service-name]
#   No argument registers every service below.
#   A service-name registers only that one (btc-usd, or "agent-bitcoin: btc-usd").
# Bitcoin suite stays bitcoin. Lightning is lightning. Nostr is nostr.
# Address check is verification. Challenge inspect is security.

set -euo pipefail

if [[ $# -gt 1 ]]; then
  echo "Usage: ./register-402index.sh [service-name]" >&2
  exit 1
fi

ONLY="${1:-}"
matched=0

register() {
  local url="$1"
  local name="$2"
  local method="$3"
  local category="$4"
  local description="$5"
  local short="${name#agent-bitcoin: }"

  if [[ -n "$ONLY" && "$ONLY" != "$name" && "$ONLY" != "$short" ]]; then
    return 0
  fi
  matched=$((matched + 1))

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

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-info" \
  "agent-bitcoin: btc-mempool-info" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core mempool size, memory, and minimum fee from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-peer-info" \
  "agent-bitcoin: btc-peer-info" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core peer count and a short address list from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-difficulty" \
  "agent-bitcoin: btc-difficulty" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core difficulty, chainwork, and blocks until the next retarget from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-block-tip" \
  "agent-bitcoin: btc-block-tip" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core tip height, block hash, and median time from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-block-header" \
  "agent-bitcoin: btc-block-header" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core block header for one height from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-tx-summary" \
  "agent-bitcoin: btc-tx-summary" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core transaction size, confirmations, and mempool fee for one txid from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-address-balance" \
  "agent-bitcoin: btc-address-balance" \
  "POST" \
  "bitcoin" \
  "Bitcoin Core confirmed UTXO balance for one address from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-uptime" \
  "agent-bitcoin: btc-uptime" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core uptime and version from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-deployment-info" \
  "agent-bitcoin: btc-deployment-info" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core active soft-fork status from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-mining-info" \
  "agent-bitcoin: btc-mining-info" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core mining summary from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-mempool-fees" \
  "agent-bitcoin: btc-mempool-fees" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core mempool minimum fee and fee bands from the operator bitcoind. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/bitcoin/btc-chain-tips" \
  "agent-bitcoin: btc-chain-tips" \
  "GET" \
  "bitcoin" \
  "Bitcoin Core chain tips from the operator bitcoind. Read-only. Lightning L402."

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

register \
  "https://agent-bitcoin.net/paid/lightning/ln-node-info" \
  "agent-bitcoin: ln-node-info" \
  "GET" \
  "lightning" \
  "Read-only LND GetInfo summary: alias, public node id, active channels, peers, height, sync, and version. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-invoice-inspect" \
  "agent-bitcoin: ln-invoice-inspect" \
  "POST" \
  "lightning" \
  "LND decode of one BOLT11 invoice. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-channel-liquidity" \
  "agent-bitcoin: ln-channel-liquidity" \
  "POST" \
  "lightning" \
  "LND channel balances for the operator node. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-peer-status" \
  "agent-bitcoin: ln-peer-status" \
  "POST" \
  "lightning" \
  "LND peer connection status for the operator node. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-path-estimate" \
  "agent-bitcoin: ln-path-estimate" \
  "POST" \
  "lightning" \
  "LND route estimate for one destination. Does not pay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-payment-status" \
  "agent-bitcoin: ln-payment-status" \
  "POST" \
  "lightning" \
  "Status of one invoice created by the operator LND. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-channel-policy" \
  "agent-bitcoin: ln-channel-policy" \
  "POST" \
  "lightning" \
  "LND local channel policy from listchannels. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-invoice-create" \
  "agent-bitcoin: ln-invoice-create" \
  "POST" \
  "lightning" \
  "Create one Lightning invoice on the operator LND. Does not pay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-preimage-verify" \
  "agent-bitcoin: ln-preimage-verify" \
  "POST" \
  "lightning" \
  "SHA-256 check that a preimage matches a payment hash. No LND. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-pay-check" \
  "agent-bitcoin: ln-pay-check" \
  "POST" \
  "lightning" \
  "Decide whether one invoice or destination is payable. Does not pay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-node-card" \
  "agent-bitcoin: ln-node-card" \
  "POST" \
  "lightning" \
  "Public graph card for one Lightning node. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-address-resolve" \
  "agent-bitcoin: ln-address-resolve" \
  "POST" \
  "lightning" \
  "Read a Lightning address pay range. Does not request an invoice. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-payee-liquidity-hint" \
  "agent-bitcoin: ln-payee-liquidity-hint" \
  "POST" \
  "lightning" \
  "Public graph capacity hint for one payee. Not channel balances. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-route-options" \
  "agent-bitcoin: ln-route-options" \
  "POST" \
  "lightning" \
  "LND route options for one destination. Does not pay. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-invoice-amount-check" \
  "agent-bitcoin: ln-invoice-amount-check" \
  "POST" \
  "lightning" \
  "LND check of whether an invoice amount is open or fixed. Read-only. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/lightning/ln-channel-reserve-check" \
  "agent-bitcoin: ln-channel-reserve-check" \
  "POST" \
  "lightning" \
  "LND channel reserve check for one peer. Read-only. Lightning L402."

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

register \
  "https://agent-bitcoin.net/paid/nostr/nostr-node-link" \
  "agent-bitcoin: nostr-node-link" \
  "POST" \
  "nostr" \
  "Public Nostr npub and whether it matches this node's Lightning id. No nsec. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/nostr/nip05-verify" \
  "agent-bitcoin: nip05-verify" \
  "POST" \
  "nostr" \
  "Check a NIP-05 name against an npub. No nsec. Lightning L402."

register \
  "https://agent-bitcoin.net/paid/nostr/nostr-profile-summary" \
  "agent-bitcoin: nostr-profile-summary" \
  "POST" \
  "nostr" \
  "Short public Nostr profile summary. No nsec and no nip05 check. Lightning L402."

if [[ -n "$ONLY" && "$matched" -eq 0 ]]; then
  echo "Unknown service: $ONLY" >&2
  exit 1
fi

echo "Done."
