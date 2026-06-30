#!/bin/bash
# Fix bind-mount ownership, then drop to user dev (container starts as root).
set -euo pipefail

CHOWN_WORK_ON_START="${CHOWN_WORK_ON_START:-1}"

chown_dev() {
  if [ -e "${1}" ]; then
    echo "==> chown dev:dev ${1}"
    if [ -d "${1}" ]; then
      chown -R dev:dev "${1}"
    elif [ -f "${1}" ]; then
      chown dev:dev "${1}"
    fi
  fi
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
    chown_dev "/home/dev/.pi"
    chown_dev "/home/dev/.cargo"
    chown_dev "/home/dev/.npm"
    chown_dev "/home/dev/.npm-global"
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
