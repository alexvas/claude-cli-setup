# syntax=docker/dockerfile:1
# Multi-stage: builder installs Claude + tools; runtime has no build proxy tooling.

ARG NODE_VERSION=22.12.0
ARG YARN_VERSION=4.15.0
ARG SOCKS_PORT=1080
ARG SOCKS_HOST=
ARG CLAUDE_TARGET=stable
ARG ASTRO_VERSION=6.4.2
ARG DEV_UID=1000
ARG DEV_GID=1000

# -----------------------------------------------------------------------------
# Builder: bootstrap, MCP, dev tools
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS builder

ARG NODE_VERSION
ARG YARN_VERSION
ARG SOCKS_PORT
ARG SOCKS_HOST
ARG CLAUDE_TARGET
ARG ASTRO_VERSION
ARG DEV_UID
ARG DEV_GID

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
RUN chmod +x /tmp/setup-dev-user.sh && DEV_UID="${DEV_UID}" DEV_GID="${DEV_GID}" /tmp/setup-dev-user.sh

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

# Rust (rustup installer is upstream-hosted; verify rustup.rs integrity out-of-band if needed)
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
    && . "$HOME/.cargo/env" \
    && cargo install --locked rust-mcp-server \
    && (cargo install --git https://github.com/camshaft/cargo-mcp --locked \
        || echo "WARN: optional cargo-mcp install failed; MCP will use rust-mcp-server")

# uv + ty CLI (uv install script is upstream-hosted; pin uv version via UV_VERSION if needed)
RUN curl -fsSL https://astral.sh/uv/install.sh | sh \
    && export PATH="${HOME}/.local/bin:${PATH}" \
    && uv tool install ty \
    && uv tool install mcp-server-git \
    && uv tool install mcp-server-fetch \
    && uv tool install mcp-server-uv

# Astro CLI (user-local npm prefix)
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH="/home/dev/.npm-global/bin:${PATH}"
RUN npm install -g "astro@${ASTRO_VERSION}"

# MCP Yarn workspace (Berry bundle downloaded at build time, not on host)
COPY --chown=dev:dev docker/mcp /home/dev/mcp
COPY --chown=dev:dev docker/setup-mcp-yarn.sh /home/dev/setup-mcp-yarn.sh
RUN YARN_VERSION="${YARN_VERSION}" bash /home/dev/setup-mcp-yarn.sh

USER root
RUN mkdir -p /home/dev/work && chown dev:dev /home/dev/work

USER dev
WORKDIR /home/dev

COPY --chown=dev:dev docker/build-mcp.sh /home/dev/build-mcp.sh
RUN YARN_VERSION="${YARN_VERSION}" WORK_ROOT=/home/dev/work GIT_REPO=/home/dev/work/proj1 bash /home/dev/build-mcp.sh

# Drop build caches and temp files before exporting to runtime
USER root
RUN rm -rf \
    /home/dev/.cargo/registry \
    /home/dev/.cargo/git \
    /home/dev/.claude/downloads \
    /home/dev/build-mcp.sh \
    /home/dev/setup-mcp-yarn.sh \
    /tmp/privoxy-for-build.conf \
    /tmp/privoxy.log

# -----------------------------------------------------------------------------
# Runtime: no build proxy tooling
# -----------------------------------------------------------------------------
FROM ubuntu:24.04 AS runtime

ARG DEV_UID=1000
ARG DEV_GID=1000
ARG YARN_VERSION=4.15.0

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/dev
ENV RUSTUP_HOME=/home/dev/.rustup
ENV CARGO_HOME=/home/dev/.cargo
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH="/home/dev/.npm-global/bin:/home/dev/.local/bin:/home/dev/.cargo/bin:/usr/local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    less \
    bat \
    curl \
    wget \
    ca-certificates \
    jq \
    ripgrep \
    python3 \
    python3-pip \
    python3-venv \
    build-essential \
    pkg-config \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && rm -rf /var/lib/apt/lists/*

# Node from builder
COPY --from=builder /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=builder /usr/local/bin/npm /usr/local/bin/npm
COPY --from=builder /usr/local/bin/npx /usr/local/bin/npx

COPY docker/setup-dev-user.sh /tmp/setup-dev-user.sh
RUN chmod +x /tmp/setup-dev-user.sh && DEV_UID="${DEV_UID}" DEV_GID="${DEV_GID}" /tmp/setup-dev-user.sh

# Dev home: only runtime-needed paths (not full .cargo registry or build temps)
COPY --from=builder --chown=dev:dev /home/dev/.claude /home/dev/.claude
COPY --from=builder --chown=dev:dev /home/dev/.claude.json /home/dev/.claude.json
COPY --from=builder --chown=dev:dev /home/dev/.local /home/dev/.local
COPY --from=builder --chown=dev:dev /home/dev/.rustup /home/dev/.rustup
COPY --from=builder --chown=dev:dev /home/dev/.cargo/bin /home/dev/.cargo/bin
COPY --from=builder --chown=dev:dev /home/dev/.npm-global /home/dev/.npm-global
COPY --from=builder --chown=dev:dev /home/dev/mcp /home/dev/mcp
COPY --from=builder /usr/local/bin/claude-bootstrap.sh /usr/local/bin/claude-bootstrap.sh

# Global yarn -> Berry bundle from MCP workspace (corepack shims break when cherry-picked)
RUN printf '#!/bin/sh\nexec node /home/dev/mcp/.yarn/releases/yarn-%s.cjs "$@"\n' "${YARN_VERSION}" \
    > /usr/local/bin/yarn \
    && chmod +x /usr/local/bin/yarn

RUN mkdir -p /home/dev/work && chown dev:dev /home/dev/work

USER dev
WORKDIR /home/dev
# Bind-mounts may be owned by a different host UID; allow git in mounted project dirs.
RUN git config --global --add safe.directory /home/dev/work \
    && git config --global --add safe.directory /home/dev/work/proj1 \
    && git config --global --add safe.directory /home/dev/work/proj2 \
    && git config --global --add safe.directory /home/dev/work/proj3
CMD ["bash"]
