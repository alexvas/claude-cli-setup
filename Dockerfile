# syntax=docker/dockerfile:1
# Multi-stage: builder installs Claude + tools; runtime has no build proxy tooling.

ARG NODE_VERSION=22.12.0
ARG YARN_VERSION=4.15.0
ARG SOCKS_PORT=1080
ARG SOCKS_HOST=
ARG CLAUDE_TARGET=stable
ARG DEV_UID=1000

# -----------------------------------------------------------------------------
# Builder: bootstrap, MCP, dev tools
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS builder

ARG NODE_VERSION
ARG YARN_VERSION
ARG SOCKS_PORT
ARG SOCKS_HOST
ARG CLAUDE_TARGET
ARG DEV_UID

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/dev
ENV PATH="/home/dev/.local/bin:/home/dev/.cargo/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    privoxy \
    curl \
    wget \
    ca-certificates \
    jq \
    ripgrep \
    build-essential \
    xz-utils \
    netcat-openbsd \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY docker/install-node.sh /tmp/install-node.sh
RUN chmod +x /tmp/install-node.sh && NODE_VERSION="${NODE_VERSION}" YARN_VERSION="${YARN_VERSION}" /tmp/install-node.sh

COPY docker/setup-dev-user.sh /tmp/setup-dev-user.sh
RUN chmod +x /tmp/setup-dev-user.sh && DEV_UID="${DEV_UID}" /tmp/setup-dev-user.sh

COPY claude.cli.agent.bootstrap.sh /usr/local/bin/claude-bootstrap.sh
RUN chmod +x /usr/local/bin/claude-bootstrap.sh

USER dev
WORKDIR /home/dev

# Fail fast: bootstrap Claude before long toolchain installs.
# Use --build-arg CLAUDE_TARGET=latest|stable|X.Y.Z for troubleshooting.
# Create local HTTP bridge (privoxy) -> upstream SOCKS, then use HTTP_PROXY/HTTPS_PROXY.
RUN test -n "${SOCKS_HOST}" \
    && cat > /tmp/privoxy-for-build.conf <<EOF
listen-address  127.0.0.1:8118
forward-socks5   / ${SOCKS_HOST}:${SOCKS_PORT} .
EOF
RUN /usr/sbin/privoxy --no-daemon /tmp/privoxy-for-build.conf >/tmp/privoxy.log 2>&1 & \
    PRIVOXY_PID=$!; \
    sleep 1; \
    export HTTP_PROXY="http://127.0.0.1:8118"; \
    export HTTPS_PROXY="${HTTP_PROXY}"; \
    export ALL_PROXY="${HTTP_PROXY}"; \
    /usr/local/bin/claude-bootstrap.sh "${CLAUDE_TARGET}"; \
    STATUS=$?; \
    if [ "${STATUS}" -ne 0 ]; then echo "=== privoxy log ==="; cat /tmp/privoxy.log; fi; \
    kill "${PRIVOXY_PID}" 2>/dev/null || true; \
    wait "${PRIVOXY_PID}" 2>/dev/null || true; \
    exit "${STATUS}"

# Rust
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
    && . "$HOME/.cargo/env" \
    && cargo install --locked rust-mcp-server \
    && (cargo install --git https://github.com/camshaft/cargo-mcp --locked 2>/dev/null || true)

# uv + ty CLI
RUN curl -fsSL https://astral.sh/uv/install.sh | sh \
    && export PATH="${HOME}/.local/bin:${PATH}" \
    && uv tool install ty \
    && uv tool install mcp-server-git \
    && uv tool install mcp-server-fetch \
    && uv tool install mcp-server-uv

# Astro CLI (user-local npm prefix)
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH="/home/dev/.npm-global/bin:${PATH}"
RUN npm install -g "astro@latest"

# MCP Yarn workspace (Berry)
WORKDIR /home/dev/mcp
RUN yarn init -2 \
    && yarn add \
        @modelcontextprotocol/server-filesystem \
        mcp-ripgrep

USER root
RUN mkdir -p /home/work && chown dev:dev /home/work

USER dev
WORKDIR /home/dev

COPY --chown=dev:dev docker/build-mcp.sh /home/dev/build-mcp.sh
RUN chmod +x /home/dev/build-mcp.sh && /home/dev/build-mcp.sh

# -----------------------------------------------------------------------------
# Runtime: no build proxy tooling
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS runtime

ARG DEV_UID=1000

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/dev
ENV PATH="/home/dev/.local/bin:/home/dev/.cargo/bin:/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    curl \
    wget \
    ca-certificates \
    jq \
    ripgrep \
    build-essential \
    xz-utils \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Node from builder
COPY --from=builder /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=builder /usr/local/bin/npm /usr/local/bin/npm
COPY --from=builder /usr/local/bin/npx /usr/local/bin/npx
COPY --from=builder /usr/local/bin/corepack /usr/local/bin/corepack
COPY --from=builder /usr/local/bin/yarn /usr/local/bin/yarn

COPY docker/setup-dev-user.sh /tmp/setup-dev-user.sh
RUN chmod +x /tmp/setup-dev-user.sh && DEV_UID="${DEV_UID}" /tmp/setup-dev-user.sh

COPY --from=builder --chown=dev:dev /home/dev /home/dev
COPY --from=builder /usr/local/bin/claude-bootstrap.sh /usr/local/bin/claude-bootstrap.sh

RUN mkdir -p /home/work && chown dev:dev /home/work

USER dev
WORKDIR /home/dev
CMD ["bash"]
