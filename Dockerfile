# syntax=docker/dockerfile:1
# BuildKit cache boundaries:
#   base -> toolchain -> pi-tools and base -> openspec-tools
# Version arguments are scoped to the stage that consumes them.

ARG DEV_UID=1000
ARG DEV_GID=1000

# -----------------------------------------------------------------------------
# Base image — resolved by the versioning resolver (NODE_BASE_IMAGE = <registry>/<repository>:<tag>@<digest>)
# -----------------------------------------------------------------------------
ARG NODE_BASE_IMAGE
FROM ${NODE_BASE_IMAGE} AS base

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

# -----------------------------------------------------------------------------
# Independently pinned prebuilt Rust tools
# -----------------------------------------------------------------------------
FROM base AS rtk-prebuilt

ARG RTK_VERSION
ARG RTK_URL
ARG RTK_SHA256
RUN curl -fsSL -o /tmp/rtk.deb "${RTK_URL}" \
    && ACTUAL=$(sha256sum /tmp/rtk.deb | cut -d' ' -f1) \
    && if [ "$ACTUAL" != "${RTK_SHA256}" ]; then echo "SHA256 mismatch: expected ${RTK_SHA256}, got $ACTUAL" >&2; exit 1; fi \
    && dpkg-deb -x /tmp/rtk.deb /tmp/rtk-extract \
    && install -m 755 /tmp/rtk-extract/usr/bin/rtk /usr/local/bin/rtk \
    && rm -rf /tmp/rtk.deb /tmp/rtk-extract

FROM base AS fd-prebuilt

ARG FD_VERSION
ARG FD_URL
ARG FD_SHA256
RUN curl -fsSL -o /tmp/fd.deb "${FD_URL}" \
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

ARG RUST_VERSION
ARG RUST_PROFILE
ARG RUST_COMPONENTS
ARG RUSTUP_URL
ARG RUSTUP_SHA256
RUN --mount=type=cache,id=cargo-registry-${DEV_UID}-${DEV_GID},target=/home/dev/.cargo/registry,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,id=cargo-git-${DEV_UID}-${DEV_GID},target=/home/dev/.cargo/git,uid=${DEV_UID},gid=${DEV_GID} \
    --mount=type=cache,id=rustup-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.rustup/downloads,uid=${DEV_UID},gid=${DEV_GID} \
    env HOME=/home/dev CARGO_HOME=/home/dev/.cargo RUSTUP_HOME=/home/dev/.rustup \
    bash -euo pipefail -c ' \
        curl -fsSL -o /tmp/rustup-init "${RUSTUP_URL}" \
        && printf "%s  %s\n" "${RUSTUP_SHA256}" /tmp/rustup-init | sha256sum -c - \
        && chmod +x /tmp/rustup-init \
        && /tmp/rustup-init -y --profile "${RUST_PROFILE}" --default-toolchain "${RUST_VERSION}" \
        && rustup component add ${RUST_COMPONENTS} \
        && ACTUAL_RUSTC="$(rustc --version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1)" \
        && test "${ACTUAL_RUSTC}" = "${RUST_VERSION}" \
        && ACTUAL_CARGO="$(cargo --version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1)" \
        && test "${ACTUAL_CARGO}" = "${RUST_VERSION}" \
        && rustfmt --version \
        && cargo clippy --version \
        && rm -f /tmp/rustup-init'

ARG UV_VERSION
ARG UV_URL
ARG UV_SHA256
RUN --mount=type=cache,id=uv-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    bash -euo pipefail -c ' \
        curl -fsSL -o /tmp/uv.tar.gz "${UV_URL}" \
        && printf "%s  %s\n" "${UV_SHA256}" /tmp/uv.tar.gz | sha256sum -c - \
        && tar xzf /tmp/uv.tar.gz -C /tmp \
        && ACTUAL_UV="$(/tmp/uv-*/uv --version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1)" \
        && test "${ACTUAL_UV}" = "${UV_VERSION}" \
        && install -D -m 755 /tmp/uv-*/uv "${HOME}/.local/bin/uv" \
        && ACTUAL_UV2="$(uv --version | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1)" \
        && test "${ACTUAL_UV2}" = "${UV_VERSION}" \
        && rm -rf /tmp/uv.tar.gz /tmp/uv-*'

ARG PYTHON_VERSION
COPY --chown=dev:dev docker/setup-python.sh /home/dev/setup-python.sh
RUN --mount=type=cache,id=uv-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    chmod +x /home/dev/setup-python.sh \
    && PYTHON_VERSION="${PYTHON_VERSION}" /home/dev/setup-python.sh

ARG TY_VERSION
RUN --mount=type=cache,id=uv-downloads-${DEV_UID}-${DEV_GID},target=/home/dev/.cache/uv,uid=${DEV_UID},gid=${DEV_GID} \
    uv tool install --python "${PYTHON_VERSION}" "ty==${TY_VERSION}"

COPY --chown=dev:dev docker/mcp /home/dev/mcp
COPY --chown=dev:dev docker/setup-mcp-yarn.sh /home/dev/setup-mcp-yarn.sh
RUN bash /home/dev/setup-mcp-yarn.sh

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

ARG OH_MY_ZSH_VERSION

COPY --from=pi-tools /opt/pi /opt/pi
COPY --from=toolchain /home/dev/.local /home/dev/.local
COPY --from=toolchain /home/dev/.rustup /home/dev/.rustup
COPY --from=toolchain /home/dev/.cargo/bin /home/dev/.cargo/bin
COPY --from=toolchain /home/dev/mcp /home/dev/mcp

RUN chown dev:dev \
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

COPY docker/zsh/zshrc.fragment /tmp/zshrc.fragment
COPY docker/setup-zsh.sh /tmp/setup-zsh.sh
RUN chmod +x /tmp/setup-zsh.sh \
    && runuser -u dev -- env HOME=/home/dev OH_MY_ZSH_VERSION="${OH_MY_ZSH_VERSION}" /tmp/setup-zsh.sh \
    && rm -f /tmp/setup-zsh.sh /tmp/zshrc.fragment

# Keep OpenSpec version changes after unrelated home and zsh setup.
COPY --from=openspec-tools /opt/openspec /opt/openspec
RUN ln -sf /opt/openspec/bin/openspec /usr/local/bin/openspec

# Effective inventory — generated by the versioning resolver
ARG EFFECTIVE_VERSIONS_FILE
RUN install -d -m 755 -o root -g root /usr/local/share/pi-cli
COPY ${EFFECTIVE_VERSIONS_FILE} /usr/local/share/pi-cli/versions.toml
RUN chown root:root /usr/local/share/pi-cli/versions.toml \
    && chmod 0444 /usr/local/share/pi-cli/versions.toml

# Runtime resolver modules for inventory-backed scripts
COPY docker/versions.py /usr/local/lib/pi-cli/docker/versions.py
COPY docker/versioning/ /usr/local/lib/pi-cli/docker/versioning/
RUN chown -R root:root /usr/local/lib/pi-cli \
    && chmod -R a+rX /usr/local/lib/pi-cli

COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

COPY docker/install-pi-extensions.sh /home/dev/install-pi-extensions.sh
RUN chmod 755 /home/dev/install-pi-extensions.sh

# Keep the image root by default: entrypoint.sh repairs bind-mount ownership and drops to dev.
WORKDIR /home/dev
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["zsh"]
