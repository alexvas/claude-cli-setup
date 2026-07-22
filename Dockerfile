# syntax=docker/dockerfile:1
# BuildKit cache boundaries:
#   base -> toolchain -> pi-tools and base -> openspec-tools
# Version arguments are scoped to the stage that consumes them.

ARG DEV_UID=1000
ARG DEV_GID=1000

# -----------------------------------------------------------------------------
# Shared runtime OS and dev-user setup
# -----------------------------------------------------------------------------
FROM node:24-trixie-slim AS base

ARG DEV_UID
ARG DEV_GID

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/dev \
    RUSTUP_HOME=/home/dev/.rustup \
    CARGO_HOME=/home/dev/.cargo \
    NPM_CONFIG_PREFIX=/home/dev/.npm-global \
    PATH="/opt/pi/bin:/opt/openspec/bin:/home/dev/.npm-global/bin:/home/dev/.local/bin:/home/dev/.cargo/bin:/usr/local/bin:${PATH}" \
    LANG=ru_RU.UTF-8 \
    LC_ALL=ru_RU.UTF-8

RUN --mount=type=cache,id=apt-cache-trixie,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-trixie,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && printf 'Binary::apt::APT::Keep-Downloaded-Packages "true";\n' > /etc/apt/apt.conf.d/keep-cache \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       git vim less bat curl wget ca-certificates jq ripgrep locales \
       openssh-client gh rpm build-essential pkg-config gosu socat bash zsh util-linux \
    && ln -sf /usr/bin/batcat /usr/local/bin/bat \
    && sed -i 's/# ru_RU.UTF-8 UTF-8/ru_RU.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen ru_RU.UTF-8 \
    && apt-get autoclean

COPY docker/setup-dev-user.sh /tmp/setup-dev-user.sh
RUN chmod +x /tmp/setup-dev-user.sh \
    && DEV_UID="${DEV_UID}" DEV_GID="${DEV_GID}" /tmp/setup-dev-user.sh \
    && rm -f /tmp/setup-dev-user.sh

# Python is installed explicitly by uv in the toolchain stage.

# -----------------------------------------------------------------------------
# Independently pinned prebuilt Rust tools
# -----------------------------------------------------------------------------
FROM base AS rtk-prebuilt

ARG RTK_VERSION=v0.43.0
ARG RTK_SHA256=eb571d784b3269521722ebe2f0dc2409e89da6bd70bf097ddb21e9d4b3b240b9
RUN URL="https://github.com/rtk-ai/rtk/releases/download/${RTK_VERSION}/rtk_amd64.deb" \
    && curl -fsSL -o /tmp/rtk.deb "$URL" \
    && ACTUAL=$(sha256sum /tmp/rtk.deb | cut -d' ' -f1) \
    && if [ "$ACTUAL" != "${RTK_SHA256}" ]; then echo "SHA256 mismatch: expected ${RTK_SHA256}, got $ACTUAL" >&2; exit 1; fi \
    && dpkg-deb -x /tmp/rtk.deb /tmp/rtk-extract \
    && install -m 755 /tmp/rtk-extract/usr/bin/rtk /usr/local/bin/rtk \
    && rm -rf /tmp/rtk.deb /tmp/rtk-extract

FROM base AS fd-prebuilt

ARG FD_VERSION=v10.4.2
ARG FD_SHA256=0e44eb5fca93f09bc6f5430b90acdf44c8e069d0a903700aeb4820629337b67b
RUN VERSION_NO_V="${FD_VERSION#v}" \
    && URL="https://github.com/sharkdp/fd/releases/download/${FD_VERSION}/fd_${VERSION_NO_V}_amd64.deb" \
    && curl -fsSL -o /tmp/fd.deb "$URL" \
    && ACTUAL=$(sha256sum /tmp/fd.deb | cut -d' ' -f1) \
    && if [ "$ACTUAL" != "${FD_SHA256}" ]; then echo "SHA256 mismatch: expected ${FD_SHA256}, got $ACTUAL" >&2; exit 1; fi \
    && dpkg-deb -x /tmp/fd.deb /tmp/fd-extract \
    && install -m 755 /tmp/fd-extract/usr/bin/fd /usr/local/bin/fd \
    && rm -rf /tmp/fd.deb /tmp/fd-extract

# -----------------------------------------------------------------------------
# Builder-only OS packages and stable toolchain setup
# -----------------------------------------------------------------------------
FROM base AS toolchain

RUN --mount=type=cache,id=apt-cache-trixie,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,id=apt-lists-trixie,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends privoxy xz-utils netcat-openbsd iproute2 \
    && apt-get autoclean

USER dev
WORKDIR /home/dev
RUN mkdir -p /home/dev/.cargo /home/dev/.rustup /home/dev/.cache/uv /home/dev/mcp

RUN --mount=type=cache,id=cargo-registry-${DEV_UID}-${DEV_GID},target=/home/dev/.cargo/registry,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,id=cargo-git-${DEV_UID}-${DEV_GID},target=/home/dev/.cargo/git,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,id=rustup-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.rustup/downloads,uid=${DEV_UID},gid=${DEV_GID} \
    env HOME=/home/dev CARGO_HOME=/home/dev/.cargo RUSTUP_HOME=/home/dev/.rustup \
    bash -euo pipefail -c 'curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain stable && rustup component add rustfmt clippy'

RUN --mount=type=cache,id=uv-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    curl -fsSL https://astral.sh/uv/install.sh | sh

ARG PYTHON_VERSION=3.14.6
COPY --chown=dev:dev docker/setup-python.sh /home/dev/setup-python.sh
RUN --mount=type=cache,id=uv-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    chmod +x /home/dev/setup-python.sh \
    && /home/dev/setup-python.sh

COPY --chown=dev:dev docker/mcp /home/dev/mcp
COPY --chown=dev:dev docker/setup-mcp-yarn.sh /home/dev/setup-mcp-yarn.sh
RUN bash /home/dev/setup-mcp-yarn.sh

# rtk and fd are now prebuilt in independent stages above.

# -----------------------------------------------------------------------------
# Independently versioned Node tool prefixes
# -----------------------------------------------------------------------------
FROM toolchain AS pi-tools

ARG PI_VERSION
USER root
RUN mkdir -p /opt/pi && chown -R dev:dev /opt/pi
USER dev
RUN --mount=type=cache,id=npm-pi-${DEV_UID}-${DEV_GID},target=/home/dev/.npm,uid=${DEV_UID},gid=${DEV_GID} \
    npm_config_cache=/home/dev/.npm npm install --global --prefix /opt/pi --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}"
RUN /opt/pi/bin/pi install git:github.com/arcanemachine/pi-read

FROM base AS openspec-tools

ARG OPENSPEC_VERSION
USER root
RUN mkdir -p /opt/openspec && chown -R dev:dev /opt/openspec
USER dev
RUN --mount=type=cache,id=npm-openspec-${DEV_UID}-${DEV_GID},target=/home/dev/.npm,uid=${DEV_UID},gid=${DEV_GID} \
    npm_config_cache=/home/dev/.npm npm install --global --prefix /opt/openspec "@fission-ai/openspec@${OPENSPEC_VERSION}"

# -----------------------------------------------------------------------------
# Runtime assembly; no builder-only packages or cache mounts are copied
# -----------------------------------------------------------------------------
FROM base AS runtime

ARG OH_MY_ZSH_VERSION=70ad5e3df8f7bed68aa6672029496926e632aedd

COPY --from=pi-tools /opt/pi /opt/pi
COPY --from=pi-tools /home/dev/.pi /home/dev/.pi
COPY --from=toolchain /home/dev/.local /home/dev/.local
COPY --from=toolchain /home/dev/.rustup /home/dev/.rustup
COPY --from=toolchain /home/dev/.cargo/bin /home/dev/.cargo/bin
COPY --from=toolchain /home/dev/mcp /home/dev/mcp

RUN chown dev:dev \
      /home/dev/.pi \
      /home/dev/.local \
      /home/dev/.rustup \
      /home/dev/.cargo \
      /home/dev/.cargo/bin \
      /home/dev/mcp \
    && ln -sf /opt/pi/bin/pi /usr/local/bin/pi \
    && install -d -o dev -g dev /home/dev/work \
    && install -d -o dev -g dev /home/dev/.npm-global \
    && install -d -o dev -g dev /home/dev/.npm-global/bin

COPY --from=rtk-prebuilt /usr/local/bin/rtk /usr/local/bin/rtk
COPY --from=fd-prebuilt /usr/local/bin/fd /usr/local/bin/fd
RUN runuser -u dev -- rtk init -g --agent pi \
    && runuser -u dev -- rtk telemetry disable

COPY docker/zsh/zshrc.fragment /tmp/zshrc.fragment
COPY docker/setup-zsh.sh /tmp/setup-zsh.sh
RUN chmod +x /tmp/setup-zsh.sh \
    && runuser -u dev -- env HOME=/home/dev OH_MY_ZSH_VERSION="${OH_MY_ZSH_VERSION}" /tmp/setup-zsh.sh \
    && rm -f /tmp/setup-zsh.sh /tmp/zshrc.fragment

# Keep OpenSpec version changes after unrelated home and zsh setup.
COPY --from=openspec-tools /opt/openspec /opt/openspec
RUN ln -sf /opt/openspec/bin/openspec /usr/local/bin/openspec

COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Keep the image root by default: entrypoint.sh repairs bind-mount ownership and drops to dev.
WORKDIR /home/dev
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["zsh"]
