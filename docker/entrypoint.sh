#!/bin/bash
# Fix bind-mount ownership, then drop to user dev (container starts as root).
set -euo pipefail

CHOWN_WORK_ON_START="${CHOWN_WORK_ON_START:-1}"

chown_dev() {
  echo "==> chown dev:dev ${1}"
  chown -R dev:dev "${1}"
}

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    for var in ${!PROJECT_PATH_@}; do
      path="${!var}"
      if [ -n "${path}" ] && [ -d "${path}" ]; then
        chown_dev "$path"
        gosu dev:dev git config --global --add safe.directory "${path}" 2>/dev/null || true
      fi
    done

    # .pi: chown everything except ide/ (tmpfs, handled separately below)
    pi_dir="/home/dev/.pi"
    if [ -d "$pi_dir" ]; then
        chown_dev "$pi_dir"
    fi
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
