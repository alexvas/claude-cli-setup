#!/bin/bash
# Fix bind-mount ownership, then drop to user dev (container starts as root).
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

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    for var in ${!PROJECT_PATH_@}; do
      path="${!var}"
      if [ -n "${path}" ] && [ -d "${path}" ]; then
        fix_ownership "$path"
        gosu dev:dev git config --global --add safe.directory "${path}" 2>/dev/null || true
      fi
    done

    # Runtime cache directories
    fix_ownership "/home/dev/.pi"
    fix_ownership "/home/dev/.cargo"
    fix_ownership "/home/dev/.npm"
    fix_ownership "/home/dev/.npm-global"
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
