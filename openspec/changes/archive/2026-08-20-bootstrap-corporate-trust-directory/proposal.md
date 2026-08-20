## Why

Corporate-trust-enabled builds fail on slim Node base images that do not yet contain `/etc/ssl/certs`, because the constructor attempts to install the replacement bundle before the `ca-certificates` package creates its parent directory. The directory must be bootstrapped before the first network operation so corporate TLS can work during package installation.

## What Changes

- Create `/etc/ssl/certs` inside the enabled corporate-trust branch before installing the validated replacement bundle.
- Preserve disabled-trust behavior without creating or changing certificate directories.
- Preserve the existing post-`ca-certificates` bundle reapplication.
- Add regression coverage for the required bootstrap order: validate bundle, create parent directory, replace system bundle, then perform the first network operation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `corporate-network-configuration`: Require enabled builds to bootstrap a missing system trust directory before replacing the bundle and before any network operation.

## Impact

- Affects the base-stage corporate trust bootstrap in `Dockerfile` and Dockerfile contract tests.
- Does not change local configuration, bundle validation, build arguments, proxy behavior, runtime mounts, or disabled-trust semantics.
