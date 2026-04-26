#!/usr/bin/env bash
# GCP startup-script — runs on every boot via google-guest-agent.
# Idempotent: each step is guarded so re-runs are no-ops.
set -euo pipefail

# --- Docker (official Debian repo) -------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

if ! dpkg -s docker-compose-plugin >/dev/null 2>&1; then
  apt-get install -y docker-compose-plugin
fi

# --- Data disk: format (once) + mount ----------------------------------------
DEV=$(readlink -f /dev/disk/by-id/google-data)
if ! blkid "$DEV" >/dev/null 2>&1; then
  mkfs.ext4 -F -L mtg-data "$DEV"
fi

mkdir -p /srv/mtg-helper/data
if ! grep -q "/srv/mtg-helper/data" /etc/fstab; then
  echo "LABEL=mtg-data /srv/mtg-helper/data ext4 defaults,nofail 0 2" >> /etc/fstab
fi
mountpoint -q /srv/mtg-helper/data || mount -a
mkdir -p /srv/mtg-helper/data/postgres /srv/mtg-helper/data/qdrant

# --- Add real users (uid >= 1000) to the docker group ------------------------
for u in $(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'); do
  usermod -aG docker "$u" || true
done
