#!/bin/sh
set -eu

PI_HOME="/home/dev/.pi"

# Guard: refuse to write to image-layer .pi
if ! mountpoint -q -- "$PI_HOME"; then
  echo "ERROR: $PI_HOME is not a mount point." >&2
  echo "The Pi home must be mounted from the host before running this script." >&2
  echo "Example: docker compose run --rm pi /home/dev/install-pi-extensions.sh" >&2
  exit 1
fi

echo "=== Pi extension setup ==="

# Validate that pi and rtk are available
command -v pi >/dev/null 2>&1 || { echo "ERROR: pi not found on PATH" >&2; exit 1; }
command -v rtk >/dev/null 2>&1 || { echo "ERROR: rtk not found on PATH" >&2; exit 1; }

# --- Pinned extension versions (change these to upgrade) ---
PI_READ_VERSION=0.2.0
PI_CODEX_USAGE_VERSION=0.9.1
PI_PROXY_VERSION=1.0.0

# --- npm-based extensions with pinned versions ---

echo "Installing @arcanemachine/pi-read@${PI_READ_VERSION} ..."
pi install "npm:@arcanemachine/pi-read@${PI_READ_VERSION}"

echo "Installing @llblab/pi-codex-usage@${PI_CODEX_USAGE_VERSION} ..."
pi install "npm:@llblab/pi-codex-usage@${PI_CODEX_USAGE_VERSION}"

echo "Installing pi-proxy@${PI_PROXY_VERSION} ..."
pi install "npm:pi-proxy@${PI_PROXY_VERSION}"

# --- rtk integration (idempotent) ---

echo "Registering rtk integration ..."
rtk init -g --agent pi
rtk telemetry disable

echo "=== Pi extension setup complete ==="
