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
python3 docker/versions.py compose config
```

## Version management

`versions.toml` is the only supported source of selected non-Debian tool
versions, revisions, URLs, and digests. Do not define those values in `.env`,
the Dockerfile, or Compose. Validate the inventory locally before building:

```bash
python3 docker/versions.py validate
```

Canonical builds always use `python3 docker/versions.py compose`. For low-level
integration, this command prints shell-safe `export` lines that can be loaded
before invoking Compose manually:

```bash
python3 docker/versions.py env
```

Pass supported overrides explicitly to the resolver:

```bash
python3 docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

Override policy is separate from the selected version in `versions.toml`. The
restricted grammar supports only `==, >, >=, <, <=` over complete numeric
`X.Y.Z` versions; comma-separated clauses are ANDed. Wildcards, OR, incomplete
versions, and prerelease values are rejected unless policy explicitly permits
them.

Update discovery is explicit and is never run by ordinary build, launch,
validation, or runtime setup paths:

```bash
python3 docker/versions.py check-updates
python3 docker/versions.py check-updates --only stages.toolchain.python --json
python3 docker/versions.py check-updates --suggest
python3 docker/versions.py check-updates --strict
python3 docker/versions.py check-updates --fail-on-outdated
```

Default mode is best-effort: unavailable providers are reported without making
builds depend on them. `--strict` makes provider failures fatal, while
`--fail-on-outdated` supports policy checks. `--suggest` is **non-mutating**: it
prints reviewable candidate values, URLs, and published checksums but never
edits the repository. Apply a suggestion to `versions.toml` manually, verify
its upstream release/checksum, run `validate`, tests, and a canonical build,
then inspect the effective inventory in the image.

Reproducibility boundary: the inventory pins non-Debian inputs, but does not
freeze Debian repositories or BuildKit metadata and does not promise a
byte-identical OCI image. Prebuilt `rtk`/`fd` installation remains owned by the
completed `split-rtk-fd-prebuilt` change; mounted-Pi-home npm extension setup
remains owned by `pin-pi-read-npm`. The shared inventory does not replace those
workflows.

## Build

Rootful Docker:

```bash
python3 docker/versions.py compose build pi
```

Rootless Docker:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

The wrapper stores the detected `HOST_GATEWAY_IP` in `.env`, preserves the runtime host mapping, and builds service `pi`.

The image exposes direct `python` and `python3` executables for the configured uv-managed CPython from any working directory. They do not run `uv run` or synchronize a project environment. There is no standalone `pip` or `pip3` command; install packages explicitly, for example `uv pip install --python "$(command -v python3)" <package>`.

Override the Python version deliberately when building:

```bash
python3 docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

For a full rebuild:

```bash
python3 docker/versions.py compose build --no-cache pi
```

### BuildKit cache verification

Use plain progress output so cached and executed steps are distinguishable:

```bash
python3 docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-build-1.log
python3 docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-build-2.log
```

The second build should be entirely cached. For targeted invalidation tests —
change a single version entry in ``versions.toml`` (e.g. bump Pi or OpenSpec),
rebuild, then revert the edit:

```bash
python3 docker/versions.py compose -- --progress plain build pi 2>&1 | tee /tmp/pi-cache-test.log
```

Changing Pi alone should rebuild only the Pi installation and final assembly
while keeping the cached OpenSpec layer. Changing OpenSpec alone should
invalidate the OpenSpec layer but retain the cached Pi installation.
Record elapsed time and ``docker image ls`` size from
these runs when comparing builders. BuildKit caches are disposable; reclaim them
normally with ``docker builder prune`` (use ``-af`` only when a full cache reset is
intended).

## Run

```bash
python3 docker/versions.py compose run --rm pi
python3 docker/versions.py compose run --rm pi pi --version
python3 docker/versions.py compose run --rm pi bash -lc 'openspec --help'
./docker/verify-runtime.sh pi-cli-pi:latest
python3 launch-pi.py
```

### Installing Pi extensions and registering rtk

Pi extensions and rtk integration are installed into the mounted host
`/home/dev/.pi` directory via a protected script — not baked into the image.
After starting the container for the first time, run:

```bash
python3 docker/versions.py compose run --rm pi /home/dev/install-pi-extensions.sh
```

The script installs pinned versions of `@arcanemachine/pi-read`,
`@llblab/pi-codex-usage`, `pi-proxy`, and registers
`rtk` for Pi. Re-running is safe — the setup is idempotent.
Without a mounted `/home/dev/.pi` the script exits with an error.

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
- **EACCES** — `CHOWN_WORK_ON_START` repairs mounted `PROJECT_PATH_*` paths and `/home/dev/.pi` when they are mount points (`mountpoint -q`). Check `DEV_UID`/`DEV_GID`, or set `CHOWN_WORK_ON_START=0` and fix permissions manually. Verify image ownership: `./docker/verify-runtime.sh pi-cli-pi:latest`.
- **Stale names** — update the wrapper and documentation; the service and commands are named `pi`.
