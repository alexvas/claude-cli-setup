## Why

`check-updates` currently sends Docker Hub manifest requests to `docker.io`, which serves the Docker website rather than the Registry API. As a result, the base Node image is always reported as unavailable because the response lacks `Docker-Content-Digest`.

## What Changes

- Normalize Docker Hub registry aliases to the canonical Registry API endpoint before authentication and manifest requests.
- Preserve configured repository and tag semantics while checking the remote manifest digest.
- Add regression coverage proving that Docker Hub checks use the Registry API and still support non-Docker-Hub registries.

## Capabilities

### New Capabilities
- `docker-registry-update-checks`: Defines reliable digest update checks against Docker Hub and other configured Docker registries.

### Modified Capabilities

None.

## Impact

- Affects `docker/versioning/providers/docker_registry.py` and its provider tests.
- Changes outbound URLs used by `./docker/versions.py check-updates` for Docker Hub only.
- No CLI, inventory schema, or dependency changes.
