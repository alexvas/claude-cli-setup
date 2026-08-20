## Context

The corporate trust contract intentionally replaces the system CA bundle before `apt-get update`, because package downloads may already traverse a corporate TLS interceptor. The selected slim Node base image can omit both the `ca-certificates` package and `/etc/ssl/certs`. The current pre-network `cp` therefore fails before APT can install the package that would normally create the directory.

The disabled path is required to preserve the base image's trust filesystem and environment unchanged.

## Goals / Non-Goals

**Goals:**
- Allow enabled corporate trust to bootstrap on a base image with no `/etc/ssl/certs` directory.
- Keep validation and replacement ahead of the first network operation.
- Preserve complete-replacement and post-package-install reapplication semantics.
- Prove bootstrap ordering with focused source-contract tests.

**Non-Goals:**
- Install `ca-certificates` before corporate trust is active.
- Change the bundle format, validation rules, source path, or runtime mount.
- Create certificate directories when corporate trust is disabled.
- Add certificates to the bundle instead of replacing it.

## Decisions

### Create the parent directory inside the enabled branch

The initial trust bootstrap will run `mkdir -p /etc/ssl/certs` after successful bundle validation and before copying the bundle. Keeping directory creation in the same enabled-only branch preserves the disabled base-image filesystem contract.

`mkdir -p` plus the existing `cp` is preferred over moving package installation earlier, which would make the first APT network request occur without corporate trust. It is also preferred over relocating the temporary trust bundle because the specification requires the system path to be replaced before network operations.

### Preserve the two-step replacement lifecycle

The initial replacement remains available to APT and other base-stage network clients. After `ca-certificates` is installed and may regenerate the system bundle, the existing second replacement remains responsible for final image contents.

### Test semantic order, not mere token presence

The Dockerfile test will locate the enabled trust bootstrap operations and assert the order `validate < mkdir < initial replacement < apt-get update`. It will also assert that directory creation belongs to the corporate-trust conditional block and precedes no disabled-path side effect.

## Risks / Trade-offs

- **[A future Dockerfile refactor makes line-based order tests brittle]** → Assert a narrow bootstrap block and semantic ordering rather than unrelated line numbers.
- **[Directory creation accidentally affects disabled builds]** → Require it to remain within the explicit enabled branch and cover that boundary in the source contract.
- **[Package installation overwrites the initial bundle]** → Preserve and test the existing post-install reapplication.
