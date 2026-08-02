## Context

The effective build projection contains the digest-pinned image `node:24-trixie-slim@sha256:ae91…`; the image reports Node `v24.18.0`, but verification derives expected `24` from the floating tag. Rust is installed through rustup with toolchain `1.97.1`; `rustfmt` resolves through `/home/dev/.cargo/bin/rustfmt` to that toolchain, but correctly reports its own `1.9.0-stable` version. Its commit `8bab26f4f6` matches `rustc`, so comparing its numeric version to `1.97.1` is semantically invalid.

## Goals / Non-Goals

**Goals:**

- Make Node expectation exact and reproducible by using a full semver image tag in inventory.
- Verify rustfmt provenance and component installation for the requested rustup toolchain.
- Preserve injectable, daemon-independent build verification.

**Non-Goals:**

- Changing the Node digest unless the exact tag is proven not to reference it.
- Replacing rustup, changing Rust installation, or requiring rustfmt's independent release number to match Rust.
- Changing runtime extension, launcher, or evidence verification.

## Decisions

### Pin Node tag as well as digest

Set the inventory tag to `24.18.0-trixie-slim` while retaining digest `sha256:ae91dcc111a68c9d2d81ff2a17bda61be126426176fde6fe7d08ab13b7f50573`. This makes the expected semver available in the immutable effective projection and preserves the current Dockerfile interface.

Reject or report floating Node tags as unsuitable for exact build-version verification rather than silently reducing comparison to a major version.

### Verify rustfmt via rustup toolchain provenance

When `rustfmt` is configured in `rust.components`, observe `rustup which rustfmt` and/or `rustup component list --toolchain <resolved-toolchain>` rather than comparing `rustfmt --version` numeric text to `rust.version`. Verify that the resolved executable belongs to the expected toolchain directory and the component is installed. Continue recording `rustfmt --version` as supplemental diagnostic output if useful, but it is not the equality contract.

This is preferred over commit-suffix equality: rustup path/component data states the actual installation relationship and does not depend on formatting of version banners.

### Preserve conditional component behavior

Do not run rustfmt observations when it is absent from the effective projection's component list. Retain the existing `clippy` contract and its expected `0.1.<Rust minor>` normalization unless independently invalidated.

## Risks / Trade-offs

- **Rustup output varies across platforms** → Parse only stable installed/path facts and test malformed output as verification failure.
- **A valid exact tag later points elsewhere** → The digest remains the immutable build authority; registry update tooling updates tag and digest together.
- **An old image remains locally tagged** → Host acceptance rebuilds the image and verifies the effective projection used by that build.
