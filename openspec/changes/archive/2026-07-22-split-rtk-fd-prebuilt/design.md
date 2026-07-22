## Context

The toolchain stage currently compiles `rtk` from a moving git revision and `fd-find` from crates.io in one sequential Cargo command. Historical measurements put this step at approximately 155.4 seconds. Official releases provide Debian amd64 packages, including `rtk` v0.43.0 and `fd` v10.4.2, with release digests available for verification.

## Goals / Non-Goals

**Goals:**

- Replace source compilation with pinned prebuilt artifacts.
- Give `rtk` and `fd` independent BuildKit stages and cache keys.
- Verify downloaded bytes before extraction or installation.
- Copy only required executables into runtime.
- Preserve `rtk init -g --agent pi` and telemetry configuration.

**Non-Goals:**

- Supporting every CPU architecture in this change; the initial implementation targets the current Debian amd64 image.
- Installing either package into the final runtime through a runtime network operation.
- Removing the Rust toolchain needed by the developer contract.

## Decisions

### Use independent prebuilt stages

Create separate `rtk-prebuilt` and `fd-prebuilt` stages derived from the common base. Each stage downloads its own pinned release, verifies its SHA-256 digest, extracts the executable, and exposes an artifact for runtime assembly. BuildKit can then execute or cache the independent stages separately.

### Prefer release `.deb` artifacts, extracted without package installation

Use the official amd64 `.deb` release assets and `dpkg-deb -x` into stage-local output directories rather than installing package metadata into the runtime. This keeps the runtime minimal while using the Debian-compatible artifacts.

The runtime build arguments SHALL be explicit and configurable:

- `RTK_VERSION=v0.43.0`, SHA-256 `eb571d784b3269521722ebe2f0dc2409e89da6bd70bf097ddb21e9d4b3b240b9`;
- `FD_VERSION=v10.4.2`, SHA-256 `0e44eb5fca93f09bc6f5430b90acdf44c8e069d0a903700aeb4820629337b67b`.

The artifact URLs and digests must be derived from these pinned version inputs or explicitly paired with them, so changing either version invalidates only its artifact stage.
### Preserve rtk integration setup

The prebuilt `rtk` executable replaces Cargo compilation, but the existing `rtk init -g --agent pi` and telemetry-disable behavior remains a separate setup step. Verify which generated files are needed and ensure they are owned by `dev`.

### Keep runtime assembly network-free

The runtime stage will use `COPY --from=rtk-prebuilt` and `COPY --from=fd-prebuilt`. It will not download or install packages itself, so runtime assembly remains deterministic and independent of network availability.

## Risks / Trade-offs

- [Upstream assets change or disappear] → Pin release versions, URLs, and SHA-256 digests; fail the build on mismatch.
- [The selected `.deb` targets amd64 only] → Make architecture scope explicit and add a separate multi-architecture design before supporting other platforms.
- [Prebuilt rtk changes integration behavior] → Run `rtk init`, verify generated integration files, and execute runtime smoke checks.
- [Git-built rtk and crates.io fd differed from release versions] → Verify tool versions and run representative `rtk` and `fd` commands before accepting the change.
- [Independent stages add Dockerfile structure] → Prefer the cache and parallelism benefits over a single sequential download stage.
