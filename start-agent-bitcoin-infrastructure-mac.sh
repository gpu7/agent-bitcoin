#!/bin/bash
echo "=== Agent-Bitcoin Mac Counterparty Setup (for AWS Backend) ==="

NETWORK=${1:-regtest}
echo "=== Starting Mac Counterparty on $NETWORK ==="

# Clean local containers (DO NOT delete volumes for pre-warming)
docker compose down --remove-orphans 2>/dev/null || true

# Start ONLY the counterparty LND on Mac
docker compose up -d agent-bitcoin-lnd

echo "=== Creating Counterparty LND Wallet (Mac) ==="
docker compose exec -it agent-bitcoin-lnd lncli --network=${NETWORK} create

echo "=== Unlocking counterparty wallet ==="
echo -e "\n" | docker compose exec -i agent-bitcoin-lnd lncli --network=${NETWORK} unlock

echo ""
echo "=== Mac Counterparty Ready for AWS Backend ==="
echo "AWS should be handling bitcoind + payment decision node."
echo ""
echo "Test the integration with:"
echo "   uv run python tests/test_aws_integration.py --backend-url http://YOUR_AWS_IP:8000"
echo ""
echo "✅ Mac counterparty is ready. You can now fund it from AWS if needed."
docker compose ps