#!/bin/bash
# Install Node MCP deps and register MCP servers for Claude Code (runs as dev after claude install).
set -euo pipefail

WORK_ROOT="${WORK_ROOT:-/home/dev/work}"
GIT_REPO="${GIT_REPO:-/home/dev/work/proj1}"
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

# Node MCP servers (deps installed here, not in package.json)
add_yarn_mcp filesystem @modelcontextprotocol/server-filesystem mcp-server-filesystem "${WORK_ROOT}"
add_yarn_mcp ripgrep mcp-ripgrep mcp-ripgrep "${WORK_ROOT}"

# Fetch + Git (official Python MCP servers)
run_mcp_add fetch uvx mcp-server-fetch

run_mcp_add git uvx mcp-server-git --repository "${GIT_REPO}"

# Rust (cargo-mcp from camshaft/cargo-mcp)
if command -v cargo-mcp >/dev/null 2>&1; then
  run_mcp_add cargo cargo-mcp
elif command -v rust-mcp-server >/dev/null 2>&1; then
  run_mcp_add cargo rust-mcp-server
fi

# Python (Astral)
run_mcp_add uv uvx mcp-server-uv

if uvx mcp-ty --help >/dev/null 2>&1; then
  run_mcp_add ty uvx mcp-ty
else
  echo "==> mcp-ty not on PyPI; ty CLI available via: ty --version"
fi

# Astro docs (remote HTTP); name must be slug-style.
claude mcp add --scope user --transport http astro-docs https://mcp.docs.astro.build/mcp

echo "==> MCP servers registered:"
claude mcp list || true
