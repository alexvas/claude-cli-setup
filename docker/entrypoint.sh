#!/bin/bash
# Fix PROJECT_PATH_* host-directory mounts, then drop to user dev (container starts as root).
# Compose/launch-pi.py define PROJECT_PATH_* as host bind mounts; mountpoint guards image paths.
set -euo pipefail

CHOWN_WORK_ON_START="${CHOWN_WORK_ON_START:-1}"

# Selectively repair ownership: find files and directories not owned by dev:dev
# and chown only those. Does NOT follow symbolic links (find default without -L).
fix_ownership() {
  if [ -e "${1}" ]; then
    echo "==> fix ownership dev:dev ${1}"
    if [ -d "${1}" ]; then
      find "${1}" \( -type f -o -type d \) \( ! -user dev -o ! -group dev \) -exec chown dev:dev {} +
    elif [ -f "${1}" ]; then
      chown dev:dev "${1}"
    fi
  fi
}

# Ensure dev user/group can read and write files and traverse directories.
# chmod X adds execute only to directories and files that are already executable.
# Does NOT follow symbolic links because find defaults to physical traversal.
fix_permissions() {
  if [ -e "${1}" ]; then
    echo "==> fix permissions ug+rwX ${1}"
    if [ -d "${1}" ]; then
      find "${1}" \( -type f -o -type d \) -exec chmod ug+rwX {} +
    elif [ -f "${1}" ]; then
      chmod ug+rwX "${1}"
    fi
  fi
}

# Apply ownership and access repair to a mounted project path.
fix_ownership_and_permissions() {
  fix_ownership "${1}"
  fix_permissions "${1}"
}

# Check whether a path is a container mount point.
# PROJECT_PATH_* variables are bind mounts by Compose contract;
# mountpoint(1) confirms the path is not an ordinary image-layer directory.
# Returns 0 for mount points, non-zero otherwise.
is_mount_point() {
  mountpoint -q -- "${1}" 2>/dev/null
}

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    if ! command -v mountpoint >/dev/null 2>&1; then
      echo "mountpoint command is required when CHOWN_WORK_ON_START is enabled" >&2
      exit 1
    fi
    # Repair project mount points and the user-provided .pi mount.
    for var in ${!PROJECT_PATH_@}; do
      path="${!var}"
      if [ -n "${path}" ] && [ -d "${path}" ] && is_mount_point "${path}"; then
        fix_ownership_and_permissions "${path}"
        gosu dev:dev git config --global --add safe.directory "${path}" 2>/dev/null || true
      fi
    done
    if [ -d /home/dev/.pi ] && is_mount_point /home/dev/.pi; then
      fix_ownership_and_permissions /home/dev/.pi
    fi
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
