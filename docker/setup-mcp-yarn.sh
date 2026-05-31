#!/bin/bash
# Bootstrap Yarn Berry bundle for MCP workspace (runs inside builder).
set -euo pipefail

YARN_VERSION="${YARN_VERSION:?YARN_VERSION required}"
MCP_DIR="${MCP_DIR:-/home/dev/mcp}"

cd "${MCP_DIR}"
mkdir -p .yarn/releases

YARN_BUNDLE=".yarn/releases/yarn-${YARN_VERSION}.cjs"
curl -fsSL "https://repo.yarnpkg.com/${YARN_VERSION}/packages/yarnpkg-cli/bin/yarn.js" \
  -o "${YARN_BUNDLE}"

cat > .yarnrc.yml <<EOF
nodeLinker: node-modules
enableGlobalCache: false
yarnPath: ${YARN_BUNDLE}
EOF
