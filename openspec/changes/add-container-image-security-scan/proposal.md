## Why

The project has no reproducible security gate for Dockerfile misconfiguration or vulnerabilities in the final runtime image. A manually triggered, report-producing workflow is needed before deciding whether this expensive and externally dependent check should become a regular CI gate.

## What Changes

- Run a Phase 0 feasibility investigation covering GitHub-hosted execution, image construction, Trivy database/cache behavior, registry access, report formats, and the minimum permissions required by a manual workflow.
- Build the ordinary final runtime image through the supported constructor, then scan it with an externally run, pinned Trivy tool; do not add Trivy to the inventory or image and do not start the project's runtime container to perform the scan.
- Add a manually triggered GitHub Actions workflow (`workflow_dispatch`) that builds the current runtime image, scans it, publishes complete reports, and exposes a clear job summary.
- Block only fixable `CRITICAL` vulnerabilities. Publish all other findings without failing the workflow.
- Permit exceptions only through a version-controlled allowlist containing a rationale and expiration date.
- Keep Hadolint and dependency-free project-specific Dockerfile unit contracts in `migrate-stage-six-verification`, outside this change.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- None.

This change adds internal security verification and CI tooling without changing the constructor's product behavior.

## Impact

- Adds Trivy as a pinned external security-tool dependency for the dedicated scan path.
- Adds GitHub Actions configuration, scanner policy, reports, cache handling, and support scripts/configuration.
- Requires Docker/BuildKit, registry/network access, and vulnerability database access only for the explicit security workflow.
- Does not add dependencies to ordinary Python unit tests, add Trivy to the reviewed inventory or runtime image, start the runtime container for scanning, or alter runtime image contents solely to satisfy scanner findings.
