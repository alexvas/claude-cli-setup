## Why

`check-updates` currently answers only whether a newer dependency version exists, so it can report an npm dependency as current while its reviewed tarball URL or integrity belongs to another artifact. The command name and result model should reflect the broader responsibility of reconciling all declaratively managed dependency records with their authoritative upstream registries.

## What Changes

- **BREAKING** Replace the `check-updates` command with `check-deps`; do not retain an alias, deprecation path, or migration hint for the old command.
- Define `deps` as the exact selected dependency records declared in `docker-constructor.toml`; exclude unrelated project dependencies, vulnerability, license, and lock-closure analysis.
- Compare both selected versions/revisions and their authoritative upstream metadata, including npm tarball URLs and SRI integrity for the current version.
- Derive npm metadata endpoints from the validated HTTPS registry base path in each reviewed artifact URL, not from its origin alone. Accept only package-aware tarball paths shaped as `/<prefix>/<package>/-/<tarball>.tgz` or `/<prefix>/@<scope>/<package>/-/<tarball>.tgz`, remove that exact package-specific suffix to obtain the registry base, and construct the metadata endpoint deterministically from the base and known package identity. Reject ambiguous paths, encoded separators or structural components, dot segments, userinfo, query or fragment components, and malformed tarball suffixes; prohibit all npm registry credentials by detecting supported credential environment variables only by safe environment name and conventional project, user, and global npm config files only by their predetermined paths; warn about `NPM_CONFIG_USERCONFIG` only by variable name without reading its value or attempting to discover its selected path; sanitize provider/transport inputs and continue credential-free without exposing secrets; and reject every cross-origin npm metadata redirect and every HTTPS downgrade.
- Replace the narrow current/outdated result semantics with `current`, `update-available`, `metadata-drift`, `integrity-mismatch`, `incomplete`, and `unavailable`; use one primary status plus typed findings when several conditions apply.
- Use the common `integrity-mismatch` status with distinct kinds for npm SRI, artifact SHA-256, and image digest mismatches.
- Make `current` mean that both version selection and all checked upstream metadata agree; suggestions for a current-version mismatch replace authoritative metadata without changing the selected version.
- Preserve informational success for `current` and `update-available`, and return failure for drift, integrity mismatch, incomplete metadata, or unavailable upstream validation.
- Extend offline `validate` with warnings for unreachable alternatives in the existing reviewed runtime artifact catalogs.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `docker-runtime`: Replace the supported facade command and define offline validation of unreachable runtime artifact alternatives.
- `docker-build-reproducibility`: Broaden dependency discovery into upstream reconciliation of declaratively managed versions and artifact metadata, including registry-derived npm checks, suggestions, and exit policy.
- `update-check-reporting`: Replace update-only statuses and command naming with dependency reconciliation statuses, typed findings, deterministic precedence, and diagnostic rendering.

## Impact

- Affects the public constructor CLI, provider/coordinator DTOs, offline inventory warnings, reporting, verification, tests, and all maintained README translations.
- Existing scripts invoking `check-updates` will fail as an unknown command and must switch to `check-deps`.
- No new third-party runtime dependency is required; upstream checks remain explicit network operations, while `validate` remains offline.
