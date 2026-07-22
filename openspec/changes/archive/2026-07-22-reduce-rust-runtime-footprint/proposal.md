## Why

The Rust toolchain currently installs the default rustup profile, and `.rustup` contributes approximately 1.58 GB to the runtime image. This increases Docker copy, export, and storage costs even though the developer contract requires only the compiler/toolchain plus explicitly supported `clippy` and `rustfmt` components.

## What Changes

- Install the Rust toolchain with rustup's minimal profile instead of the default profile.
- Add `rustfmt` and `clippy` explicitly so both remain available to developers.
- Preserve runtime availability of `cargo`, `rustc`, `rustfmt`, `cargo clippy`, `rtk`, and `fd`.
- Extend runtime verification to assert the required Rust commands and components.
- Measure `.rustup` size and Docker build/export time before and after the change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-runtime`: The runtime Rust toolchain SHALL use a minimal profile while explicitly retaining the required `rustfmt` and `clippy` components and exposing the documented Rust commands.

## Impact

- `Dockerfile` Rust installation and runtime assembly.
- `docker/verify-runtime.sh` runtime checks.
- Docker image size, build cache behavior, and export time.
- Rust developer tooling available inside the container remains compatible, with optional default-profile components no longer installed.
