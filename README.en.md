[ Русский ](README.md) | **English** | [ 中文 ](README.zh.md)

# Pi Docker runtime

An isolated Docker environment for the π coding agent and development tools.

## Requirements

- Docker Engine 24+ with BuildKit
- Docker Compose v2 (`docker compose`)

## Contents

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage Pi and developer-tool image |
| `docker-compose.yml` | Compose service `pi` |
| `docker/compose.proj2.yml`, `docker/compose.proj3.yml` | Optional project mounts |
| `docker/build_wrapper.py` | Host-gateway diagnostics and build wrapper |
| `launch-pi.py` | Project-selection TUI and container launcher |
| `.env.example` | Configuration template |

The image includes `pi`, OpenSpec, Rust, `uv`, `ty`, `rtk`, `fd`, Yarn Berry, MCP, git, zsh, vim, jq, ripgrep, and other tools. The container runs as user `dev`; `DEV_UID`/`DEV_GID` must match the host file owner.

## Setup

```bash
cp .env.example .env
```

Set in `.env`:

- `PROJECT_PATH_1` — required first project path;
- `PROJECT_PATH_2`, `PROJECT_PATH_3` — optional additional projects;
- `COMPOSE_FILE` — the base Compose file plus required fragments;
- `HOST_GATEWAY_IP` — host address for rootless Docker, usually set by the wrapper;
- `DEV_UID`, `DEV_GID` — the container `dev` user's UID/GID.

`SOCKS_PORT`, `SOCKS_HOST`, and `EXTERNAL_IP` are no longer used for image builds and are not part of the supported interface. Runtime access to host services uses `host.docker.internal`.

Check the rendered configuration (it may contain secrets):

```bash
docker compose config
```

## Build

Rootful Docker:

```bash
docker compose build pi
```

Rootless Docker:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

The wrapper stores the detected `HOST_GATEWAY_IP` in `.env`, preserves the runtime host mapping, and builds service `pi`.

For a full rebuild:

```bash
docker compose build --no-cache pi
```

## Run

```bash
docker compose run --rm pi
docker compose run --rm pi pi --version
docker compose run --rm pi bash -lc 'openspec --help'
python3 launch-pi.py
```

`launch-pi.py` selects up to three projects and runs `docker compose run ... pi`. Additional projects are mounted through the fragments in `docker/`.

## Shell prompt

The only supported prompt file is `/home/dev/.pi-zsh-prompt`. Other prompt files are not loaded.

## Docker storage cleanup

Old prompt names may remain in layers of older rootless Docker images. Do not delete files manually under `~/.local/share/docker/containerd/`. Inspect storage first:

```bash
docker system df -v
```

Then prune build cache or unused images as needed:

```bash
docker builder prune
# more aggressively:
# docker builder prune -af
# docker image prune -a
```

Do not use `--volumes` unless you have verified that no required data is stored there.

## Troubleshooting

- **No host gateway** — run `python3 docker/build_wrapper.py diagnose`; for rootless Docker, run `apply -y` if needed.
- **Missing additional project** — set `PROJECT_PATH_2`/`PROJECT_PATH_3` and add the corresponding fragment to `COMPOSE_FILE`.
- **EACCES** — check `DEV_UID`/`DEV_GID`, or set `CHOWN_WORK_ON_START=0` and fix permissions manually.
- **Stale names** — update the wrapper and documentation; the service and commands are named `pi`.
