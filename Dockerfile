# syntax=docker/dockerfile:1
# Multi-stage: builder installs Claude + tools; runtime has no build proxy tooling.

ARG SOCKS_PORT=1080
ARG HOST_GATEWAY_IP=
ARG SOCKS_HOST=
ARG EXTERNAL_IP=
ARG DEV_UID=1000
ARG DEV_GID=1000

# -----------------------------------------------------------------------------
# Builder: bootstrap, MCP, dev tools
# -----------------------------------------------------------------------------
FROM node:24-bookworm-slim AS builder

ARG SOCKS_PORT
ARG HOST_GATEWAY_IP
ARG SOCKS_HOST
ARG EXTERNAL_IP
ARG DEV_UID
ARG DEV_GID
ARG PI_VERSION
ARG OPENSPEC_VERSION

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

COPY docker/setup-dev-user.sh /tmp/setup-dev-user.sh
RUN chmod +x /tmp/setup-dev-user.sh && DEV_UID="${DEV_UID}" DEV_GID="${DEV_GID}" /tmp/setup-dev-user.sh

USER dev
WORKDIR /home/dev

# Rust (rustup installer is upstream-hosted; verify rustup.rs integrity out-of-band if needed)
# 1. Заранее создаем родительские папки от имени пользователя dev
RUN mkdir -p /home/dev/.cargo /home/dev/.rustup

# 2. Теперь монтируем кеш в уже существующие папки
RUN --mount=type=cache,target=/home/dev/.cargo/registry,uid=1000,gid=1000 \
    --mount=type=cache,target=/home/dev/.cargo/git,uid=1000,gid=1000 \
    --mount=type=cache,target=/home/dev/.rustup/downloads,uid=1000,gid=1000 \
    env HOME=/home/dev CARGO_HOME=/home/dev/.cargo RUSTUP_HOME=/home/dev/.rustup \
    bash -euo pipefail -c 'curl -fsSL https://sh.rustup.rs | sh -s -- -y --default-toolchain stable && . "$HOME/.cargo/env"'

# uv + ty CLI (uv install script is upstream-hosted; pin uv version via UV_VERSION if needed)
RUN --mount=type=cache,target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    curl -fsSL https://astral.sh/uv/install.sh | sh \
    && export PATH="${HOME}/.local/bin:${PATH}" \
    && uv tool install ty

# MCP Yarn workspace (Berry bundle downloaded at build time, not on host)
COPY --chown=dev:dev docker/mcp /home/dev/mcp
COPY --chown=dev:dev docker/setup-mcp-yarn.sh /home/dev/setup-mcp-yarn.sh
RUN bash /home/dev/setup-mcp-yarn.sh

USER root

RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent@${PI_VERSION}
RUN npm install -g @fission-ai/openspec@${OPENSPEC_VERSION}
RUN cargo install --git https://github.com/rtk-ai/rtk \
  && rtk init -g --agent pi \
  && rtk telemetry disable \
  && cargo install fd-find

RUN mkdir -p /home/dev/work && chown dev:dev /home/dev/work

USER dev
WORKDIR /home/dev

# Drop build caches and temp files before exporting to runtime
USER root
RUN rm -rf \
    /home/dev/.cargo/registry \
    /home/dev/.cargo/git \
    /home/dev/.rustup/downloads \
    /home/dev/setup-mcp-yarn.sh \
    /tmp/privoxy-for-build.conf \
    /tmp/privoxy.log

# -----------------------------------------------------------------------------
# Runtime: no build proxy tooling
# -----------------------------------------------------------------------------
FROM node:24-bookworm-slim AS runtime

ARG DEV_UID=1000
ARG DEV_GID=1000
ARG OH_MY_ZSH_VERSION=70ad5e3df8f7bed68aa6672029496926e632aedd

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/dev
ENV RUSTUP_HOME=/home/dev/.rustup
ENV CARGO_HOME=/home/dev/.cargo
ENV NPM_CONFIG_PREFIX=/home/dev/.npm-global
ENV PATH="/home/dev/.npm-global/bin:/home/dev/.local/bin:/home/dev/.cargo/bin:/usr/local/bin:${PATH}"
ENV LANG=ru_RU.UTF-8
ENV LC_ALL=ru_RU.UTF-8

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
    bash \
    zsh \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen ru_RU.UTF-8 \
    && rm -rf /var/lib/apt/lists/*

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
COPY --from=builder /home/dev/.pi /home/dev/.pi
COPY --from=builder /home/dev/.local /home/dev/.local
COPY --from=builder /home/dev/.rustup /home/dev/.rustup
COPY --from=builder /home/dev/.cargo/bin /home/dev/.cargo/bin
COPY --from=builder /home/dev/mcp /home/dev/mcp
COPY --from=builder /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js /usr/local/bin/pi
RUN ln -sf /usr/local/lib/node_modules/@fission-ai/openspec/bin/openspec.js /usr/local/bin/openspec

RUN mkdir -p /home/dev/work && chown dev:dev /home/dev/work \
  && mkdir -p /home/dev/.npm-global/bin && chown dev:dev /home/dev/.npm-global \
  && mkdir -p /home/dev/.pi && chown -R dev:dev /home/dev/.pi

COPY docker/zsh/zshrc.fragment /tmp/zshrc.fragment
COPY docker/setup-zsh.sh /tmp/setup-zsh.sh
RUN chmod +x /tmp/setup-zsh.sh \
    && runuser -u dev -- env HOME=/home/dev OH_MY_ZSH_VERSION="${OH_MY_ZSH_VERSION}" /tmp/setup-zsh.sh \
    && rm -f /tmp/setup-zsh.sh /tmp/zshrc.fragment

USER dev
WORKDIR /home/dev
RUN pi install git:github.com/arcanemachine/pi-read

USER root

COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
WORKDIR /home/dev
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["zsh"]
