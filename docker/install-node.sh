#!/bin/bash
set -euo pipefail

NODE_VERSION="${NODE_VERSION:?NODE_VERSION required}"
ARCH="$(uname -m)"
case "${ARCH}" in
  x86_64) NODE_ARCH="x64" ;;
  aarch64|arm64) NODE_ARCH="arm64" ;;
  *) echo "Unsupported arch: ${ARCH}" >&2; exit 1 ;;
esac

NODE_TARBALL="node-v${NODE_VERSION}-linux-${NODE_ARCH}.tar.xz"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}"

curl -fsSL "${NODE_URL}" -o "/tmp/${NODE_TARBALL}"
tar -xJf "/tmp/${NODE_TARBALL}" -C /usr/local --strip-components=1
rm -f "/tmp/${NODE_TARBALL}"

corepack enable
corepack prepare "yarn@${YARN_VERSION:?YARN_VERSION required}" --activate

node --version
yarn --version
