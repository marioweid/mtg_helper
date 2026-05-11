#!/usr/bin/env bash
# GCP startup-script — runs on every boot via google-guest-agent.
# Idempotent: each step is guarded so re-runs are no-ops.
set -euo pipefail

# --- google-guest-agent: enable OS Login + metadata key sync ----------------
# Some debian-12 images ship the unit disabled. Without it, OS Login keys
# uploaded via `gcloud compute ssh` never appear in the SA's profile and the
# CI deploy fails with "Permission denied (publickey)".
if ! systemctl is-enabled --quiet google-guest-agent; then
  systemctl enable --now google-guest-agent
fi

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

# --- Repo lives on the data disk so it survives VM replacement (spot preempt,
# image upgrades, etc). Symlink /opt/mtg-helper → /srv/mtg-helper/data/repo.
if [ ! -L /opt/mtg-helper ]; then
  rm -rf /opt/mtg-helper
  ln -s /srv/mtg-helper/data/repo /opt/mtg-helper
fi

# --- Add real users (uid >= 1000) to the docker group ------------------------
for u in $(getent passwd | awk -F: '$3 >= 1000 && $3 < 65534 {print $1}'); do
  usermod -aG docker "$u" || true
done

# --- GitHub Actions self-hosted runner ---------------------------------------
# Runner files live on the data disk so spot recreates reuse the existing
# registration. The systemd unit is installed once via `svc.sh install` (see
# README/runbook); on every boot we just re-enable + start it. If the runner
# was never registered the unit doesn't exist yet — skip silently.
if [ -d /srv/mtg-helper/data/runner ] && [ ! -e /opt/actions-runner ]; then
  ln -s /srv/mtg-helper/data/runner /opt/actions-runner
fi

RUNNER_SVC=$(systemctl list-unit-files 'actions.runner.*.service' --no-legend | awk '{print $1}' | head -1)
if [ -n "$RUNNER_SVC" ]; then
  systemctl enable --now "$RUNNER_SVC"
fi

# --- Atuin (shell history) — system-wide install -----------------------------
if ! command -v atuin >/dev/null 2>&1; then
  ATUIN_VERSION=$(curl -fsSL https://api.github.com/repos/atuinsh/atuin/releases/latest \
    | grep -m1 '"tag_name"' | cut -d'"' -f4)
  ARCH=$(uname -m)
  TARBALL="atuin-${ARCH}-unknown-linux-gnu.tar.gz"
  TMP=$(mktemp -d)
  curl -fsSL "https://github.com/atuinsh/atuin/releases/download/${ATUIN_VERSION}/${TARBALL}" \
    -o "${TMP}/atuin.tar.gz"
  tar -xzf "${TMP}/atuin.tar.gz" -C "${TMP}"
  install -m 0755 "${TMP}/atuin-${ARCH}-unknown-linux-gnu/atuin" /usr/local/bin/atuin
  rm -rf "${TMP}"
fi

# Bash system-wide init (idempotent; only loads for interactive shells).
if ! grep -q 'atuin init bash' /etc/bash.bashrc; then
  cat >> /etc/bash.bashrc <<'EOF'

# atuin shell history
if [[ $- == *i* ]] && command -v atuin >/dev/null 2>&1; then
  eval "$(atuin init bash --disable-up-arrow)"
fi
EOF
fi

# --- Bring the stack up. Containers also have restart: unless-stopped, so
# subsequent reboots are no-ops; this handles the cold-start case (initial
# bootstrap, boot-disk replacement, post-`docker compose down`).
if [ -f /opt/mtg-helper/.env.prod ] && [ -f /opt/mtg-helper/docker-compose.prod.yml ]; then
  cd /opt/mtg-helper
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
  docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d
fi
