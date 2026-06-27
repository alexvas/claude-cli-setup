#!/bin/bash
# Bootstrap Yarn Berry bundle for MCP workspace (runs inside builder).
set -euo pipefail

MCP_DIR="${MCP_DIR:-/home/dev/mcp}"

cd "${MCP_DIR}"

cat > .yarnrc.yml <<EOF
nodeLinker: node-modules
enableGlobalCache: false
EOF
