#!/usr/bin/env bash
# Apply rootless-Docker port-forward override and run gateway diagnosis.
# Requires: rootless Docker (systemctl --user docker.service) and
# docker-gateway host-access mode enabled in docker-constructor.toml.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEST_DIR="${HOME}/.config/systemd/user/docker.service.d"
DEST_FILE="${DEST_DIR}/override.conf"

mkdir -p "${DEST_DIR}"
cp "${SCRIPT_DIR}/rootless-docker.override.conf" "${DEST_FILE}"
echo "Installed ${DEST_FILE}"

systemctl --user daemon-reload
systemctl --user restart docker.service
echo "Restarted docker.service (rootless). Waiting for daemon..."
sleep 3
docker info 2>/dev/null | grep -i rootless || true

echo "Verifying host reachability from container (ephemeral probe server):"
exec python3 "${ROOT_DIR}/docker/docker-constructor.py" doctor
