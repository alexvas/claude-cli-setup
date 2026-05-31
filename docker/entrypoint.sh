#!/bin/bash
# Fix bind-mount ownership, then drop to user dev (container starts as root).
set -euo pipefail

CHOWN_WORK_ON_START="${CHOWN_WORK_ON_START:-1}"

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    for dir in /home/dev/work /home/dev/work/proj1 /home/dev/work/proj2 /home/dev/work/proj3; do
      if [ -d "${dir}" ]; then
        echo "==> chown dev:dev ${dir}"
        chown -R dev:dev "${dir}"
      fi
    done
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
