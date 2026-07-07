#!/bin/bash
echo "=== Trying to connect Mac LND to AWS LND ==="

AWS_IP=${1:-100.56.101.253}   # Pass IP as argument if needed

while true; do
  echo "Trying connect to $AWS_IP..."
  if docker compose -f docker-compose.regtest.mac.yml exec -T agent-bitcoin-lnd lncli --lnddir=/home/lnd/.lnd --network=regtest connect 022c3c33f5974b37861859de0417bf8f95fba55dae3677053c2aa6f9aaa2032b67@${AWS_IP}:9735; then
    echo "✅ Connected!"
    break
  fi
  echo "Not ready yet. Retrying in 60 seconds..."
  sleep 60
done
