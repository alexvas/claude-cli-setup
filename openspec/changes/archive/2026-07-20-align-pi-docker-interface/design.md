## Context

The executable Compose service is `pi`, and the Dockerfile installs the Pi coding agent. However, `docker/build_wrapper.py` still invokes service `claude`; all README translations document `claude`; OpenSpec's build-networking requirement preserves that obsolete command; and several comments and shell filenames retain the old product identity. Compose also passes SOCKS/gateway build arguments that the Dockerfile declares but never consumes. Runtime `extra_hosts` is still required for host proxy/model access and must not be confused with obsolete build-time proxy setup.

## Goals / Non-Goals

**Goals:**
- Make every supported build/run path target service `pi`.
- Distinguish required runtime host connectivity from removed build-time proxy claims.
- Make all maintained documentation describe the current Pi image and launcher.
- Remove stale names where they have no compatibility value.

**Non-Goals:**
- Redesign rootless host probing or runtime model routing.
- Change project mounts, launcher behavior, or the `pi` CLI itself.
- Introduce a compatibility alias service named `claude`.

## Decisions

### Make `pi` the single canonical service name

The wrapper, examples, troubleshooting commands, specs, and translated READMEs use `pi`. A temporary `claude` alias was considered but rejected because it would prolong ambiguity and create duplicate Compose service maintenance.

### Remove only unused build-time network plumbing

Audit each `SOCKS_PORT`, `SOCKS_HOST`, `EXTERNAL_IP`, and `HOST_GATEWAY_IP` occurrence. Remove Compose build args and Dockerfile declarations that have no consumer. Retain `HOST_GATEWAY_IP` persistence and `extra_hosts` where runtime containers use `host.docker.internal` to reach host services. Update wrapper wording so probing is described as runtime host-reachability preparation, not as a SOCKS-assisted image bootstrap.

### Rewrite documentation from current behavior

Use the Dockerfile, Compose file, launcher, and current specs as sources of truth rather than mechanically replacing `claude` with `pi`. Keep Russian, English, and Chinese documents structurally aligned, including requirements, build commands, launcher usage, included tools, environment variables, and troubleshooting.

### Rename internal legacy labels only when safe

Rename `.claude-cli-zsh-prompt` and related comments if no external mount or documented compatibility relies on the path. If compatibility is useful, read the new Pi path first and temporarily fall back to the old path while documenting deprecation.

## Risks / Trade-offs

- [Removing legacy environment variables surprises existing users] → Call out removals in documentation; values are currently inert at build time.
- [A broad README rewrite introduces translation drift] → Keep headings and command blocks parallel and validate referenced files/services mechanically.
- [Renaming the prompt fragment loses user customization] → Provide a fallback or migration copy when the legacy file exists.
- [Removing build arguments overlaps cache optimization work] → Apply interface cleanup before or coordinate it with `optimize-docker-build-cache` to avoid editing the same declarations twice.
