#!/bin/bash
set -e

echo "=== Mounting NVMe SSD on m5d.large ==="

# Check for NVMe device
if [ ! -b /dev/nvme1n1 ]; then
  echo "❌ NVMe device /dev/nvme1n1 not found. Are you on m5d.large?"
  exit 1
fi

echo "✅ NVMe device found."

# Create mount point
sudo mkdir -p /mnt/nvme

# Format only if not already formatted (safe check)
if ! sudo blkid /dev/nvme1n1 | grep -q ext4; then
  echo "⚠️  Formatting NVMe (this is safe on instance store)..."
  sudo mkfs -t ext4 /dev/nvme1n1
fi

# Mount it
sudo mount /dev/nvme1n1 /mnt/nvme
sudo chown -R ubuntu:ubuntu /mnt/nvme
echo "✅ Mounted to /mnt/nvme"

# Move Docker data to NVMe (persistent)
echo "Moving Docker data to NVMe..."
sudo systemctl stop docker

sudo mv /var/lib/docker /mnt/nvme/docker 2>/dev/null || true
sudo mkdir -p /mnt/nvme/docker
sudo ln -sfn /mnt/nvme/docker /var/lib/docker

# Make mount persistent across reboots
echo "/dev/nvme1n1 /mnt/nvme ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab

sudo systemctl start docker

echo "✅ Docker now using NVMe SSD!"
echo "You can now run ./startup.sh"
