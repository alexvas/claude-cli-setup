## Context

The toolchain stage installs Rust with rustup's default profile. The runtime copies `/home/dev/.rustup`, which is approximately 1.58 GB and adds measurable Docker copy, export, and storage cost. The runtime contract exposes `cargo`, while the developer contract also requires `rustc`, `rustfmt`, and `cargo clippy`.

## Goals / Non-Goals

**Goals:**

- Use rustup's minimal profile as the baseline installation.
- Explicitly install and retain `rustfmt` and `clippy`.
- Preserve `cargo`, `rustc`, `rustfmt`, and `cargo clippy` in the runtime image.
- Verify required Rust tools and components during runtime smoke checks.
- Measure footprint and build/export improvements.

**Non-Goals:**

- Removing the Rust toolchain from the runtime.
- Replacing rustup or the stable Rust toolchain.
- Changing the build products or behavior of `rtk` and `fd`.

## Decisions

### Install minimal profile, then add required components

Invoke rustup with `--profile minimal` and explicitly add `rustfmt` and `clippy` to the selected stable toolchain. This removes optional default-profile content while making the developer contract explicit. Do not rely on the installer default profile or on components being transitively present.

The exact command sequence must work with the configured `RUSTUP_HOME` and `CARGO_HOME`, and component installation must occur before `cargo install` builds `rtk` and `fd`.

### Keep the Rust toolchain in runtime

Continue copying `.rustup` and the required Cargo binaries into runtime because developers need `cargo`, `rustc`, `rustfmt`, and `cargo clippy`, not merely the prebuilt `rtk` and `fd` binaries.

### Verify commands and components directly

Runtime verification will check command resolution and successful version output for `cargo`, `rustc`, and `rustfmt`, and will run `cargo clippy --version`. It will also assert that the active toolchain reports both `clippy` and `rustfmt` components where rustup metadata is available.

### Measure before and after

Record `.rustup` and total image sizes, Rust copy duration, and representative build/export times. Compare against the existing approximately 1.58 GB `.rustup` and recorded build baseline. Keep the minimal-profile change only if required tooling remains functional and the measurements show a meaningful reduction.

## Risks / Trade-offs

- [The minimal profile omits a component needed by a developer] → Explicitly install `rustfmt` and `clippy`; verify both in the image.
- [Component installation selects a toolchain different from the active default] → Install components for the configured stable toolchain and assert the active toolchain during verification.
- [Rustup metadata or component layout changes] → Prefer stable CLI checks and keep failures actionable; do not silently skip required components.
- [The size reduction is smaller than expected] → Record separate `.rustup` and image measurements before changing scope.
