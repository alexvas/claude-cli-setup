## Why

Pi extensions are currently registered during Docker image assembly, while the runtime mounts the host's `/home/dev/.pi` over the image-provided extension directory. This hides image-installed extensions and makes extension registration occur in the wrong filesystem; the supported extensions need a repeatable, user-executable setup step after the host mount is present.

## What Changes

- Remove Pi extension installation and registration commands from `Dockerfile`.
- Add `docker/install-pi-extensions.sh` as the single extension setup script.
- Have the script install or register `@llblab/pi-codex-usage`, `pi-proxy`, and the pinned npm `pi-read` package.
- Have the script register `rtk` integration for Pi.
- Copy the script into `/home/dev/install-pi-extensions.sh` as `root:root`, readable and executable by `dev` but not writable by `dev`.
- Pin every npm-installed extension version in the script; use immutable Git references or explicit registration for Git-based extensions.
- Verify extension setup and rtk registration against the mounted runtime home.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-caching`: Pi extension setup SHALL be removed from image assembly so extension changes do not contaminate unrelated image layers.
- `docker-runtime`: The runtime SHALL provide a protected extension setup script that installs/registers the supported Pi extensions and rtk integration after runtime mounts are available.

## Impact

- `Dockerfile` runtime assembly and Pi tools stage.
- New `docker/install-pi-extensions.sh` runtime setup script.
- Host-mounted `/home/dev/.pi` contents and Pi extension discovery.
- npm/Git extension sources, explicit version pins, and runtime setup workflow.
