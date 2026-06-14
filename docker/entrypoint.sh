#!/bin/bash
# Fix bind-mount ownership, then drop to user dev (container starts as root).
set -euo pipefail

CHOWN_WORK_ON_START="${CHOWN_WORK_ON_START:-1}"

if [ "$(id -u)" = "0" ]; then
  if [ "${CHOWN_WORK_ON_START}" = "1" ] || [ "${CHOWN_WORK_ON_START}" = "true" ]; then
    for var in ${!PROJECT_PATH_@}; do
      path="${!var}"
      if [ -n "${path}" ] && [ -d "${path}" ]; then
        echo "==> chown dev:dev ${path}"
        chown -R dev:dev "${path}"
        gosu dev:dev git config --global --add safe.directory "${path}" 2>/dev/null || true
      fi
    done

    # .claude: chown everything except ide/ (tmpfs, handled separately below)
    if [ -d /home/dev/.claude ]; then
      echo "==> chown dev:dev /home/dev/.claude (skipping ide/)"
      find /home/dev/.claude -not -path '/home/dev/.claude/ide/*' -not -path '/home/dev/.claude/ide' -exec chown dev:dev {} + 2>/dev/null || true
    fi

    # ide/: tmpfs (Docker creates it as root:root), fix ownership before dropping to dev
    mkdir -p -m 0700 /home/dev/.claude/ide
    chown dev:dev /home/dev/.claude/ide
  fi

  # Register git MCP server for the mounted project (path known only at runtime)
  if [ -n "${PROJECT_PATH_1:-}" ] && [ -d "${PROJECT_PATH_1}" ]; then
    echo "==> Registering git MCP server for ${PROJECT_PATH_1}"
    gosu dev:dev claude mcp add --scope user --transport stdio git -- uvx mcp-server-git --repository "${PROJECT_PATH_1}" || true
  fi

  exec gosu dev:dev "$@"
fi

exec "$@"
