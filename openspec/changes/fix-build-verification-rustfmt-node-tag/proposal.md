## Why

Build verification currently reports false failures for a correctly built image: the inventory pins a digest but uses the floating Node tag `24-trixie-slim`, while the verifier requires exact Node semver; it also compares rustfmt's independent `1.9.0-stable` version to the Rust toolchain version `1.97.1`. Verification must prove the intended pinned artifacts rather than reject valid toolchain components.

## What Changes

- Pin the Node inventory tag to the exact `24.18.0-trixie-slim` tag associated with the existing digest.
- Require Node build verification to compare the installed Node semver against the exact semver encoded in the resolved inventory image tag.
- Replace the invalid rustfmt-version-equals-Rust-version contract with verification that rustfmt is the installed rustup component of the resolved Rust toolchain.
- Retain exact verification of `rustc`, `cargo`, and `clippy`, including conditional Rust component checks.
- Add daemon-independent verification fixtures for floating tags, exact tags, rustfmt's independent version string, wrong/missing rustfmt components, and toolchain mismatches.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-build-reproducibility`: Clarify exact Node tag pinning and Rust component provenance requirements for build verification.

## Impact

- Affects `docker-constructor.toml`, generated effective build projection expectations, `docker/versioning/verification.py`, and build-verification tests.
- Does not change the Dockerfile's declarative `NODE_BASE_IMAGE` input, runtime verification, project-launcher behavior, or Docker-host execution semantics.
