# syntax=docker/dockerfile:1
# Multi-stage: builder installs Claude + tools; runtime has no build proxy tooling.

ARG NODE_VERSION=22.12.0
ARG YARN_VERSION=4.15.0
ARG SOCKS_PORT=1080
ARG HOST_GATEWAY_IP=
ARG SOCKS_HOST=
ARG EXTERNAL_IP=
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
ARG HOST_GATEWAY_IP
ARG SOCKS_HOST
ARG EXTERNAL_IP
ARG CLAUDE_TARGET
ARG ASTRO_VERSION
ARG DEV_UID
ARG DEV_GID

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/dev
ENV PATH="/home/dev/.local/bin:/home/dev/.cargo/bin:${PATH}"

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
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

COPY --chmod=755 docker/bootstrap-claude-build.sh /tmp/bootstrap-claude-build.sh
# Fail fast: bootstrap Claude before long toolchain installs.
# Use --build-arg CLAUDE_TARGET=latest|stable|X.Y.Z for troubleshooting.
RUN HOST_GATEWAY_IP="${HOST_GATEWAY_IP}" SOCKS_HOST="${SOCKS_HOST}" EXTERNAL_IP="${EXTERNAL_IP}" \
       SOCKS_PORT="${SOCKS_PORT}" CLAUDE_TARGET="${CLAUDE_TARGET}" \
       /tmp/bootstrap-claude-build.sh

# Rust (rustup installer is upstream-hosted; verify rustup.rs integrity out-of-band if needed)
USER root
RUN --mount=type=cache,target=/cache/cargo/registry,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,target=/cache/cargo/git,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,target=/cache/rustup/downloads,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,target=/cache/cargo-target,uid=${DEV_UID},gid=${DEV_GID} \
    mkdir -p /home/dev/.cargo /home/dev/.rustup \
    && chown -R dev:dev /home/dev/.cargo /home/dev/.rustup \
    && ln -sf /cache/cargo/registry /home/dev/.cargo/registry \
    && ln -sf /cache/cargo/git /home/dev/.cargo/git \
    && ln -sf /cache/rustup/downloads /home/dev/.rustup/downloads \
    && runuser -u dev -- env HOME=/home/dev CARGO_HOME=/home/dev/.cargo RUSTUP_HOME=/home/dev/.rustup \
        bash -euo pipefail -c '\
      curl -fsSL https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
      && . "$HOME/.cargo/env" \
      && CARGO_TARGET_DIR=/cache/cargo-target cargo install --locked rust-mcp-server \
      && (CARGO_TARGET_DIR=/cache/cargo-target cargo install --git https://github.com/camshaft/cargo-mcp --locked \
          || echo "WARN: optional cargo-mcp install failed; MCP will use rust-mcp-server")'
USER dev

# uv + ty CLI (uv install script is upstream-hosted; pin uv version via UV_VERSION if needed)
RUN --mount=type=cache,target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    curl -fsSL https://astral.sh/uv/install.sh | sh \
    && export PATH="${HOME}/.local/bin:${PATH}" \
    && uv tool install ty \
    && uv tool install mcp-server-git \
    && uv tool install mcp-server-fetch \
    && uv tool install mcp-server-uv

# Astro CLI (user-local npm prefix)
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH="/home/dev/.npm-global/bin:${PATH}"
RUN --mount=type=cache,target=/home/dev/.npm,uid=${DEV_UID},gid=${DEV_GID} \
    npm install -g "astro@${ASTRO_VERSION}"

# MCP Yarn workspace (Berry bundle downloaded at build time, not on host)
COPY --chown=dev:dev docker/mcp /home/dev/mcp
COPY --chown=dev:dev docker/setup-mcp-yarn.sh /home/dev/setup-mcp-yarn.sh
RUN YARN_VERSION="${YARN_VERSION}" bash /home/dev/setup-mcp-yarn.sh

USER root
RUN mkdir -p /home/dev/work && chown dev:dev /home/dev/work

USER dev
WORKDIR /home/dev

COPY --chown=dev:dev docker/build-mcp.sh /home/dev/build-mcp.sh
RUN --mount=type=cache,target=/home/dev/mcp/.yarn/cache,uid=${DEV_UID},gid=${DEV_GID} \
    YARN_VERSION="${YARN_VERSION}" WORK_ROOT=/home/dev/work bash /home/dev/build-mcp.sh

# Drop build caches and temp files before exporting to runtime
USER root
RUN rm -rf \
    /home/dev/.cargo/registry \
    /home/dev/.cargo/git \
    /home/dev/.rustup/downloads \
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
ARG OH_MY_ZSH_VERSION=70ad5e3df8f7bed68aa6672029496926e632aedd

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/dev
ENV RUSTUP_HOME=/home/dev/.rustup
ENV CARGO_HOME=/home/dev/.cargo
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH="/home/dev/.npm-global/bin:/home/dev/.local/bin:/home/dev/.cargo/bin:/usr/local/bin:${PATH}"
ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8
# Отключаем телеметрию Claude Code
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    vim \
    less \
    bat \
    curl \
    wget \
    ca-certificates \
    jq \
    ripgrep \
    locales \
    openssh-client \
    gh \
    rpm \
#   Do not use python3 from apt; python3 is provided via uv (see /etc/profile.d/dev-python.sh)
#   Do not use python3-pip, use uv pip instead
#   Do not use python3-venv, use uv venv instead
    build-essential \
    pkg-config \
    gosu \
    socat \
    zsh \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen ru_RU.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

# Node from builder (npm/npx shims must point at npm-cli.js, not broken copied scripts)
COPY --from=builder /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# python3/pip via uv (no system python3 package).
# NOTE: python3 is a thin wrapper around "uv run python" — arbitrary packages
# are NOT available unless installed with "uv pip install --system <pkg>" or
# the working directory is a uv-managed project with the dependency declared.
RUN printf '#!/bin/sh\nexec uv run python "$@"\n' > /usr/local/bin/python3 \
    && chmod +x /usr/local/bin/python3 \
    && printf '%s\n' \
    "alias python3='uv run python'" \
    "alias pip='uv pip --system'" \
    > /etc/profile.d/dev-python.sh

COPY docker/setup-dev-user.sh /tmp/setup-dev-user.sh
RUN chmod +x /tmp/setup-dev-user.sh && DEV_UID="${DEV_UID}" DEV_GID="${DEV_GID}" /tmp/setup-dev-user.sh

# Dev home: only runtime-needed paths (not full .cargo registry or build temps)
COPY --from=builder --chown=dev:dev /home/dev/.claude /home/dev/.claude
COPY --chown=dev:dev docker/claude-settings/keybindings.json /home/dev/.claude/keybindings.json
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

COPY docker/zsh/zshrc.fragment /tmp/zshrc.fragment
COPY docker/setup-zsh.sh /tmp/setup-zsh.sh
RUN chmod +x /tmp/setup-zsh.sh \
    && runuser -u dev -- env HOME=/home/dev OH_MY_ZSH_VERSION="${OH_MY_ZSH_VERSION}" /tmp/setup-zsh.sh \
    && rm -f /tmp/setup-zsh.sh /tmp/zshrc.fragment

USER dev
WORKDIR /home/dev

USER root
COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
WORKDIR /home/dev
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["zsh"]
