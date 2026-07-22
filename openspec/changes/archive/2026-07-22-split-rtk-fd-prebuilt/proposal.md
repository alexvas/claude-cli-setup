## Why

The Docker build currently compiles `rtk` and `fd` sequentially in one Cargo step that costs approximately 155 seconds. Both projects publish Linux release artifacts, so compiling them in the image duplicates work already performed upstream and prevents independent caching.

## What Changes

- Replace in-image Cargo compilation of `rtk` and `fd` with pinned upstream prebuilt Linux artifacts.
- Add explicit build arguments `RTK_VERSION=v0.43.0` and `FD_VERSION=v10.4.2` as the initial release pins.
- Download and verify each artifact independently with an expected SHA-256 digest.
- Build `rtk` and `fd` in separate independent Docker stages so BuildKit can cache and execute them independently.
- Copy only the required executables into the runtime image.
- Preserve `rtk init -g --agent pi` integration setup and telemetry-disabled behavior.
- Verify tool versions, executable availability, and artifact integrity during the build/runtime checks.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-caching`: Rust CLI artifacts SHALL come from pinned upstream releases with verified digests and independent cache boundaries instead of one combined source-build step.
- `docker-runtime`: The runtime SHALL continue exposing functional `rtk` and `fd` commands and their existing integrations.

## Impact

- `Dockerfile` build graph, network downloads, and runtime assembly.
- Build cache boundaries and image build/export time.
- Removal of Cargo compilation requirements for these two tools after the toolchain stage has completed.
- Upstream release availability and architecture selection become build inputs.
