#!/bin/bash

dnf update -y
dnf install -y docker

systemctl enable docker
systemctl start docker

while [ ! -b /dev/nvme1n1 ]; do
  echo "Esperando por /dev/nvme1n1..."
  sleep 2
done

# Formatear el disco SOLO si no tiene un sistema de archivos previo
blkid /dev/nvme1n1 || mkfs -t xfs /dev/nvme1n1

mkdir -p /data/qdrant

mount /dev/nvme1n1 /data/qdrant

echo "/dev/nvme1n1 /data/qdrant xfs defaults,nofail 0 2" >> /etc/fstab

docker run -d \
  --name qdrant \
  --restart unless-stopped \
  -p 6333:6333 \
  -e QDRANT__SERVICE__API_KEY="${qdrant_api_key}" \
  -v /data/qdrant:/qdrant/storage \
  qdrant/qdrant
