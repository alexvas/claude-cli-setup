## Context

The Docker Registry update provider builds API URLs directly from the inventory's `registry` field. The base image uses the familiar image-name host `docker.io`, but Docker Hub exposes its Registry V2 API at `registry-1.docker.io`. Requests therefore return an HTML website response with HTTP 200 instead of a manifest and are misclassified as missing a digest header.

## Goals / Non-Goals

**Goals:**
- Route Docker Hub authentication probes and manifest requests to its canonical Registry API endpoint.
- Keep custom registry behavior unchanged.
- Cover endpoint selection and digest discovery with offline provider tests.

**Non-Goals:**
- Discover newer image tags or Node major versions.
- Add authenticated Docker Hub account support beyond the existing bearer-token flow.
- Change the inventory's user-facing registry notation or migrate `versions.toml`.

## Decisions

- Normalize known Docker Hub aliases inside the provider before constructing any URL. This keeps the inventory readable and ensures both the `/v2/` auth probe and manifest request use the same endpoint. Changing `versions.toml` alone was rejected because other inventories may validly use the conventional `docker.io` alias.
- Limit normalization to Docker Hub aliases and pass all other registry hosts through unchanged. General redirect or registry discovery was rejected as unnecessary complexity and could create security ambiguity around credential destinations.
- Assert complete request URLs in provider tests. This catches regressions that response-only fakes would otherwise hide.

## Risks / Trade-offs

- [Docker Hub changes its canonical API hostname] → Keep endpoint normalization isolated so the mapping can be updated in one place.
- [A custom deployment intentionally uses a host spelled `docker.io`] → Treating this globally recognized alias as Docker Hub is consistent with container tooling conventions; custom registries must use their actual hostname.
- [Cached website responses remain after the fix] → The normalized URL creates a distinct cache key, so stale `docker.io` responses are not reused.
