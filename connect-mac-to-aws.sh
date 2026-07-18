#!/bin/bash
echo "=== Trying to connect Mac LND to AWS LND ==="

# Require IP as argument
if [ -z "$1" ]; then
    echo "Usage: $0 <AWS_IP>"
    echo "Example: $0 98.92.94.104"
    exit 1
fi

AWS_IP=$1
LND_PUBKEY="022c3c33f5974b37861859de0417bf8f95fba55dae3677053c2aa6f9aaa2032b67"

echo "Connecting to AWS LND at $AWS_IP:9735 ..."

while true; do
    echo "Trying connect to $AWS_IP..."
    if docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd \
        lncli --lnddir=/home/lnd/.lnd --network=regtest connect ${LND_PUBKEY}@${AWS_IP}:9735; then
        echo "✅ Successfully connected to AWS node!"
        break
    fi
    echo "Not ready yet. Retrying in 60 seconds..."
    sleep 60
done
