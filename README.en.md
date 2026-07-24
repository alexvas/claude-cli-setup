[ Русский ](README.md) | **English** | [ 中文 ](README.zh.md)

# Pi Docker runtime

An isolated Docker environment for Pi and development tools. Selected non-Debian inputs live in `versions.toml`; do not duplicate their versions in README files, `.env`, Dockerfile, or Compose.

## Requirements

- Docker Engine 24+ with BuildKit
- Docker Compose v2
- Python 3 on the host

## 1. Build the environment

Validate the reviewed inventory, then build service `pi`:

```bash
./docker/versions.py validate
./docker/versions.py compose build pi
```

The build needs no project path or `.env`. For rootless Docker host-gateway diagnostics, use:

```bash
python3 docker/build_wrapper.py diagnose
python3 docker/build_wrapper.py apply -y
python3 docker/build_wrapper.py build -y
```

`./docker/versions.py env` prints shell-safe resolved build inputs for low-level integration. A deliberate Python override uses:

```bash
./docker/versions.py compose --override stages.toolchain.python.version=X.Y.Z -- build pi
```

Override constraints accept only `==, >, >=, <, <=` with complete `X.Y.Z` versions. Wildcards, incomplete versions, OR expressions, and prerelease values are rejected unless policy explicitly allows them. The inventory pins reviewed non-Debian inputs, but Debian repositories and BuildKit metadata mean byte-identical OCI output is not guaranteed.

## 2. Launch the environment

Open the interactive project selector:

```bash
./launch-pi.py
```

The selected main project becomes the container working directory and is bind-mounted at the same absolute path. Up to two additional projects may be selected as optional 1:1 mounts. Host `~/.pi` is mounted at `/home/dev/.pi`. Set optional `BASE_PROJECT_DIR` in `.env` or pass `--base-project-dir` to choose the TUI tree root.

Low-level runtime commands remain available when `PROJECT_PATH_1` is set:

```bash
./docker/versions.py compose run --rm pi
```

## 3. Update environment components

### Update Pi after a release

1. Inspect only Pi and request a reviewable suggestion:

   ```bash
   ./docker/versions.py check-updates --only stages.pi-tools.pi --suggest
   ```

2. `--suggest` is **non-mutating**: verify the upstream release and manually apply the accepted value and related metadata to `stages.pi-tools.pi` in `versions.toml`.
3. Validate and review the exact repository change:

   ```bash
   ./docker/versions.py validate
   git diff -- versions.toml
   ```

4. Rebuild and verify the runtime image:

   ```bash
   ./docker/versions.py compose build pi
   ./docker/verify-runtime.sh pi-cli-pi:latest
   ```

### Managed component lifecycle

| Category | Representative components | Installation location / owner | Update source |
|---|---|---|---|
| Base image | Node base | Image-owned OCI layers | Docker registry metadata in `versions.toml` |
| Toolchain | Rust, uv, Python, ty | Builder/image-owned paths | Rust channel, GitHub, uv, PyPI providers |
| Node CLIs | Pi, OpenSpec | Image-owned global tools | npm provider |
| Prebuilt binaries | rtk, fd | Image-owned runtime binaries | GitHub release artifacts and checksums |
| Shell runtime | Oh My Zsh | Image-owned `/home/dev` content | Git revision provider |
| Pi extensions | pi-read, usage, proxy, rtk registration | Host-mounted `/home/dev/.pi` | `runtime.pi-extensions` npm metadata |
| Debian packages | OS utilities and libraries | Image-owned system paths | APT; outside `versions.toml` update discovery |

For another managed component, locate its inventory path, run `check-updates --only <path> --suggest`, review and edit manually, validate, inspect the diff, rebuild, and verify. If the path is under `runtime.pi-extensions`, rebuilding updates the effective image inventory but not mounted state; refresh it under Maintenance.

### Update-check controls

- **Interactive review:** `--only <provider-or-path>` narrows discovery; `--suggest` adds non-mutating TOML candidates.
- **Automation and policy:** `--json` emits machine-readable output; `--strict` fails on provider errors; `--fail-on-outdated` fails when an update exists.
- **Advanced discovery/cache:** `--include-prerelease` includes prerelease results; `--cache-ttl`, `--cache-dir`, and `--no-cache` control update-discovery HTTP caching.

Ordinary builds, validation, launch, and extension setup never perform update discovery.

## Maintenance

### Verify the image

```bash
./docker/verify-runtime.sh pi-cli-pi:latest
```

### Refresh mounted Pi extensions

After changing `runtime.pi-extensions`, launch with the intended Pi home mounted and run the protected, idempotent installer:

```bash
./docker/versions.py compose run --rm pi /home/dev/install-pi-extensions.sh
```

### Repair host ownership and permissions

With rootless Docker, `EACCES` can occur in two situations:

1. The agent inside the container cannot modify a file created by the host user.
2. The host user cannot modify or read a file created inside the container.

To grant both sides the required access, assign the target directory to the `docker-dev` user and group, then allow the owner and group to read and write:

```bash
sudo chown -R <docker-dev>:<docker-dev> /path/you-intend-to-own
chmod -R ug+rwX /path/you-intend-to-own
```

In a rootless Docker configuration, the `docker-dev` user and group typically correspond to UID/GID `100999`. The host user must also be added to the `docker-dev` group:

```bash
sudo usermod -aG <docker-dev> "$USER"
```

Confirm the actual UID/GID before running these commands, and limit recursive permission changes to the directory you intend to own.

### Clean Docker storage and caches

Inspect usage, then remove only disposable build cache:

```bash
docker system df -v
docker builder prune
```

Use `docker builder prune -af` or `docker image prune -a` only when a full cache/image reset is intended. Avoid `--volumes` unless all stored data is known to be disposable.

## Troubleshooting

- **EACCES on a mounted project or Pi home:** compare host ownership with the configured runtime UID/GID. Either let `CHOWN_WORK_ON_START=1` repair actual mount points or disable it and use the narrowly scoped Maintenance procedure above.
- **Update provider unavailable:** retry later or inspect cached results; use `--strict` only when provider availability must be enforced.
