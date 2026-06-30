#!/bin/bash
# Fix bind-mount ownership and permissions, then drop to user dev (container starts as root).
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

# Selectively add group-write permission: find files and directories missing g+w
# and chmod only those. Does NOT follow symbolic links (find default without -L).
fix_group_write() {
  if [ -e "${1}" ]; then
    echo "==> fix g+w ${1}"
    if [ -d "${1}" ]; then
      find "${1}" \( -type f -o -type d \) ! -perm -g+w -exec chmod g+w {} +
    elif [ -f "${1}" ]; then
      chmod g+w "${1}"
    fi
  fi
}

# Apply both ownership repair and group-write permission repair to a path.
fix_ownership_and_group_write() {
  fix_ownership "${1}"
  fix_group_write "${1}"
}

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    for var in ${!PROJECT_PATH_@}; do
      path="${!var}"
      if [ -n "${path}" ] && [ -d "${path}" ]; then
        fix_ownership_and_group_write "$path"
        gosu dev:dev git config --global --add safe.directory "${path}" 2>/dev/null || true
      fi
    done

    # Runtime cache directories
    fix_ownership_and_group_write "/home/dev/.pi"
    fix_ownership_and_group_write "/home/dev/.cargo"
    fix_ownership_and_group_write "/home/dev/.npm"
    fix_ownership_and_group_write "/home/dev/.npm-global"
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
