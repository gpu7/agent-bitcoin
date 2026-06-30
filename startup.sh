#!/bin/bash
set -e

echo "=== Agent-Bitcoin Startup (m5d Optimized) ==="

# Mount NVMe
if [ -b /dev/nvme1n1 ] && ! mountpoint -q /mnt/nvme; then
  echo "→ Mounting NVMe SSD..."
  sudo mkdir -p /mnt/nvme
  sudo mount /dev/nvme1n1 /mnt/nvme 2>/dev/null || {
    echo "Formatting NVMe..."
    sudo mkfs -t ext4 /dev/nvme1n1
    sudo mount /dev/nvme1n1 /mnt/nvme
  }
  sudo chown -R ubuntu:ubuntu /mnt/nvme

  # Move Docker to NVMe
  if [ ! -L /var/lib/docker ]; then
    sudo systemctl stop docker docker.socket
    sudo mv /var/lib/docker /mnt/nvme/docker 2>/dev/null || true
    sudo mkdir -p /mnt/nvme/docker
    sudo ln -sfn /mnt/nvme/docker /var/lib/docker
    sudo systemctl start docker
  fi

  echo "/dev/nvme1n1 /mnt/nvme ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab > /dev/null
  echo "✅ NVMe mounted + Docker using it"
fi

# Start services
echo "Starting services..."
docker compose -f docker-compose.regtest.yml up -d

sleep 5

echo "✅ Services started."
echo ""
echo "LND Commands:"
echo "   Create wallet (first time):"
echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd create"
echo ""
echo "   Unlock wallet:"
echo "   docker exec -it agent-payment-decision-lnd lncli --lnddir=/home/lnd/.lnd unlock"
echo ""
echo "Test API:"
echo "   curl http://localhost:8000/balance"
