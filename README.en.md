[ Русский ](README.md) | **English** | [ 中文 ](README.zh.md)

This project is a runtime environment for running the Claude CLI agent in an isolated Docker container.

## Requirements

- Docker Engine 24+ with [BuildKit](https://docs.docker.com/build/buildkit/) (enabled by default in modern installations)
- Docker Compose v2 (`docker compose`, not `docker-compose` v1)

## Contents

| File | Purpose |
|------|---------|
| [claude.cli.agent.bootstrap.sh](claude.cli.agent.bootstrap.sh) | Claude Code installer (used during image build) |
| [Dockerfile](Dockerfile) | Multi-stage image: Ubuntu 24.04, Claude, MCP, tools |
| [docker-compose.yml](docker-compose.yml) | `claude` service, variables from `.env` |
| [docker/compose.proj2.yml](docker/compose.proj2.yml) | Optional mount for `PROJECT_PATH_2` (1:1 as on host) |
| [docker/compose.proj3.yml](docker/compose.proj3.yml) | Optional mount for `PROJECT_PATH_3` (1:1 as on host) |
| [.env.example](.env.example) | Configuration template |
| [docker/build_wrapper.py](docker/build_wrapper.py) | Network setup (host gateway + SOCKS) and image build |

The image is built for the `dev` user (UID/GID from `DEV_UID` / `DEV_GID`, default 1000). During the build stage, the host SOCKS proxy (`0.0.0.0:${SOCKS_PORT}`) is accessible from the build container via the host gateway IP. With **rootful** Docker, `docker compose build` is sufficient (the gateway is detected automatically). With **rootless** — [docker/build_wrapper.py](docker/build_wrapper.py) determines `HOST_GATEWAY_IP` via an ephemeral HTTP probe.

The image includes: Python via `uv` (`python3` command — wrapper/alias for `uv run python`), Yarn Berry, `vim`, `less`, `bat`, `git`, `openssh-client`, `gh`, `rpmbuild` (`rpm` package), MCP servers for filesystem, ripgrep, fetch, git, Rust (stable), uv/ty, Astro CLI, `build-essential`, `ru_RU.UTF-8` locale, and remote Astro documentation.

## Setup

1. Copy the configuration:

```bash
cp .env.example .env
```

2. Edit `.env`:

- `SOCKS_PORT` — SOCKS proxy port on the **host** (for downloading Claude during build; the proxy must listen on `0.0.0.0:${SOCKS_PORT}`).
- `HOST_GATEWAY_IP` — optional. **Rootful:** leave unset (compose uses `host-gateway`, Dockerfile detects the bridge IP). **Rootless:** set by `docker/build_wrapper.py build` after probing.
- `PROJECT_PATH_1` — **required** path to the first project on the host.
- `PROJECT_PATH_2`, `PROJECT_PATH_3` — optional; include fragments via `COMPOSE_FILE` (see below).
- **Rootless Docker:** use [docker/build_wrapper.py](docker/build_wrapper.py); if needed, it will suggest [docker/apply-rootless-port-forward.sh](docker/apply-rootless-port-forward.sh).
- `CLAUDE_TARGET` — Claude installer target during build: `stable`, `latest`, or a specific version `X.Y.Z` (default `stable`).
- `DEV_UID`, `DEV_GID` — UID/GID of the user inside the container; **must** match the owner of the project directory on the host (`id -u` / `id -g`), otherwise the bind-mount will be root-owned and git inside the container will break.

3. The host must have SOCKS available (during build).

### Host projects (1–3 directories)

| Scenario | `COMPOSE_FILE` in `.env` |
|----------|---------------------------|
| One project | `docker-compose.yml` |
| Two projects | `docker-compose.yml:docker/compose.proj2.yml` (+ `PROJECT_PATH_2`) |
| Three projects | `…:docker/compose.proj2.yml:docker/compose.proj3.yml` (+ `PROJECT_PATH_3`) |

Container paths match host paths (1:1 bind-mount).

Verify the final configuration (secrets are substituted from `.env`; **do not publish** the output if it contains keys):

```bash
docker compose config
```

## Security

- Do not commit `.env` or store API keys in the repository.
- `docker compose config` reveals substituted variable values — do not paste this output into tickets or CI logs.
- Rotate the API key if leaked; update `.env` and restart the container.
- The image is built with SOCKS access only during the build stage.

## Building the image

A SOCKS proxy on the host is required (`0.0.0.0:${SOCKS_PORT}`).

### Rootful Docker (default)

```bash
docker compose build claude
```

### Rootless Docker

Wrapper: diagnostics → systemd override if needed → write `.env` → build:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

The `-y`/`--yes` flag can be placed before or after the subcommand (`-y build` or `build -y`).

Manual rootless build (if `HOST_GATEWAY_IP` is already in `.env`):

```bash
docker compose build claude
```

Different Claude version at build time:

```bash
CLAUDE_TARGET=latest docker compose build claude
```

Full rebuild without cache:

```bash
docker compose build --no-cache claude
```

## Docker Compose commands

| Command | Purpose |
|---------|---------|
| `docker compose build claude` | Build the image |
| `docker compose build --no-cache claude` | Build the image from scratch |
| `docker compose run claude` | Start the container (bash by default); container persists after exit |
| `docker compose run --rm claude` | Same, but remove the container after exit |
| `docker compose run --rm claude claude` | Launch Claude CLI immediately |
| `docker compose run --rm claude bash -lc 'claude --version'` | Check Claude installation |
| `docker compose run --rm claude bash -lc 'claude mcp list'` | List MCP servers |

The `--rm` flag is convenient for one-off sessions; without it, the container can be restarted via `docker compose start`.

## Container environment variables

When running `docker compose run`, the following are passed to the container (from `.env`):

- `ANTHROPIC_BASE_URL` ← Anthropic-compatible API URL (direct endpoint or proxy)
- `ANTHROPIC_AUTH_TOKEN` ← API key (optional)
- `ANTHROPIC_MODEL` ← from `.env` (default `deepseek-v4-pro[1m]`)
- `ANTHROPIC_DEFAULT_OPUS_MODEL`, `ANTHROPIC_DEFAULT_SONNET_MODEL` ← DeepSeek
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL` ← deepseek-flash or local Ollama/llamacpp model
- `CLAUDE_CODE_EFFORT_LEVEL` ← from `.env`

## Troubleshooting

- **Build fails at bootstrap** — check `SOCKS_PORT` (SOCKS on the host must listen on `0.0.0.0`). Rootful: `docker compose build claude` without `build_wrapper`. Rootless: `python3 docker/build_wrapper.py diagnose`; if needed, `docker/apply-rootless-port-forward.sh`.
- **Missing second project in the container** — set `PROJECT_PATH_2` and add `docker/compose.proj2.yml` to `COMPOSE_FILE`.
- **Empty `PROJECT_PATH_2` in compose** — do not include the `compose.proj2.yml` fragment unless the path is set.
- **EACCES when writing to the working directory** — by default, the entrypoint runs `chown -R dev:dev` on mounted directories at startup (`CHOWN_WORK_ON_START=1`). This also changes file ownership on the host. To disable: `CHOWN_WORK_ON_START=0` in `.env` and align permissions on the host manually (`chown` + `DEV_UID`/`DEV_GID` = `id -u` / `id -g`).
