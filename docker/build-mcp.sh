#!/bin/bash
# Register MCP servers for Claude Code (run as dev after claude install).
set -euo pipefail

WORK_ROOT="${WORK_ROOT:-/home/work}"
MCP_DIR="${MCP_DIR:-/home/dev/mcp}"

mkdir -p "${WORK_ROOT}"

run_mcp_add() {
  local name="$1"
  shift
  echo "==> claude mcp add: ${name}"
  claude mcp add --transport stdio "${name}" -- "$@"
}

# Node / Yarn (packages in ${MCP_DIR}/node_modules)
run_mcp_add filesystem \
  yarn --cwd "${MCP_DIR}" dlx @modelcontextprotocol/server-filesystem "${WORK_ROOT}"

run_mcp_add ripgrep \
  yarn --cwd "${MCP_DIR}" dlx mcp-ripgrep "${WORK_ROOT}"

# Fetch + Git (official Python MCP servers)
run_mcp_add fetch uvx mcp-server-fetch

run_mcp_add git uvx mcp-server-git --repository "${WORK_ROOT}"

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
claude mcp add --transport http astro-docs https://mcp.docs.astro.build/mcp

echo "==> MCP servers registered:"
claude mcp list || true
