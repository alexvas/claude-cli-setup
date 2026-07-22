## 1. Install a minimal Rust toolchain

- [x] 1.1 Change the rustup installation to use the minimal profile while retaining the configured stable toolchain
- [x] 1.2 Explicitly install `rustfmt` and `clippy` for the active stable toolchain before compiling Rust tools
- [x] 1.3 Confirm `cargo install` for `rtk` and `fd-find` still succeeds with the minimal profile and explicit components

## 2. Preserve and verify the runtime contract

- [x] 2.1 Keep the required Rust toolchain and Cargo binaries in the runtime image without restoring optional default-profile components
- [x] 2.2 Extend `docker/verify-runtime.sh` to check `cargo`, `rustc`, `rustfmt`, and `cargo clippy --version`
- [x] 2.3 Add actionable failure output when `rustfmt` or `clippy` is unavailable

## 3. Measure and document the reduction

- [x] 3.1 Build the default and custom-UID/GID images and verify the Rust developer contract
- [x] 3.2 Measure `.rustup`, image size, Rust copy/export time, and representative build time before and after the profile change
- [x] 3.3 Record verification results and update maintained documentation with the retained Rust components
- [x] 3.4 Run strict OpenSpec validation and the project verification checks
