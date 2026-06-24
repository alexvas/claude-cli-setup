#!/bin/bash
# Install Node MCP deps and register MCP servers for Claude Code (runs as dev after claude install).
set -euo pipefail

WORK_ROOT="${WORK_ROOT:-/home/dev/work}"
MCP_DIR="${MCP_DIR:-/home/dev/mcp}"
YARN_VERSION="${YARN_VERSION:-4.15.0}"
YARN_BIN="${MCP_DIR}/.yarn/releases/yarn-${YARN_VERSION}.cjs"
MCP_BIN="${MCP_DIR}/node_modules/.bin"

mkdir -p "${WORK_ROOT}"

if [[ ! -f "${YARN_BIN}" ]]; then
  echo "Yarn Berry bundle not found: ${YARN_BIN}; run setup-mcp-yarn.sh first" >&2
  exit 1
fi

run_mcp_add() {
  local name="$1"
  shift
  echo "==> claude mcp add: ${name}"
  claude mcp add --scope user --transport stdio "${name}" -- "$@"
}

# name package bin_name [server args...]
add_yarn_mcp() {
  local name="$1"
  local package="$2"
  local bin_name="$3"
  shift 3

  echo "==> yarn add: ${package}"
  node "${YARN_BIN}" --cwd "${MCP_DIR}" add "${package}"

  local bin_path="${MCP_BIN}/${bin_name}"
  if [[ ! -x "${bin_path}" ]]; then
    echo "Expected bin not found after yarn add: ${bin_path}" >&2
    exit 1
  fi

  run_mcp_add "${name}" "${bin_path}" "$@"
}

echo "==> MCP servers registered:"
claude mcp list || true
