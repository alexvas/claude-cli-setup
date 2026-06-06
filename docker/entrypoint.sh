#!/bin/bash
# Fix bind-mount ownership, then drop to user dev (container starts as root).
set -euo pipefail

CHOWN_WORK_ON_START="${CHOWN_WORK_ON_START:-1}"

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    for path in "${PROJECT_PATH_1:-}" "${PROJECT_PATH_2:-}" "${PROJECT_PATH_3:-}"; do
      if [ -n "${path}" ] && [ -d "${path}" ]; then
        echo "==> chown dev:dev ${path}"
        chown -R dev:dev "${path}"
        gosu dev:dev git config --global --add safe.directory "${path}" 2>/dev/null || true
      fi
    done
  fi
  exec gosu dev:dev "$@"
fi

exec "$@"
