## Context

See proposal.md for motivation. The repository builds through the direct constructor facade and currently has no GitHub workflow or image vulnerability policy. Trivy requires external vulnerability data whose contents change independently of the repository, while a complete final-image scan requires a real Docker/BuildKit build and registry/network access. Hadolint and repository-specific Dockerfile contracts are owned by `migrate-stage-six-verification`.

## Goals / Non-Goals

**Goals:**
- Prove the security workflow is feasible on the selected GitHub runner before committing to its final topology.
- Scan repository configuration and the final runtime image with a reproducibly pinned Trivy tool version.
- Publish complete evidence while failing only for non-exempt, fixable `CRITICAL` vulnerabilities.
- Keep execution manual and isolated from ordinary unit tests.

**Non-Goals:**
- Run on every push or pull request in the initial rollout.
- Add Hadolint, replace project-specific Dockerfile contracts, or change application behavior.
- Claim that a passing scan proves the image is vulnerability-free.
- Automatically modify the Dockerfile, inventory, dependencies, or allowlist in response to findings.

## Decisions

### Make Phase 0 a blocking feasibility gate

Before implementing the durable workflow, record an executable preflight on a GitHub-hosted Linux runner that establishes:

- Docker Engine and Buildx versions and BuildKit availability;
- successful construction of the current final runtime image through the supported constructor path;
- successful pinned Trivy configuration and image scans;
- vulnerability database download, cache persistence, and cold/warm timings;
- registry/network behavior and expected credentials/rate limits;
- usable JSON, SARIF, human-readable summary, and uploaded artifact outputs;
- minimum GitHub token permissions and artifact retention behavior;
- disk consumption and cleanup requirements.

The durable workflow topology and pinned versions shall be selected from this evidence. Phase 0 must not silently weaken the confirmed vulnerability policy when a runner limitation is found.

Alternative considered: design the final workflow directly from assumptions about hosted runners. Rejected because image size, database caching, permissions, and output support materially affect reliability and cost.

### Use Trivy for both configuration and final-image scanning

Use one immutably pinned Trivy release/container image for repository misconfiguration/secret-oriented checks and image package vulnerabilities. Trivy provides both scanner classes and avoids introducing a separate Syft/Grype SBOM pipeline in the initial change.

Alternative considered: Grype with Syft. Rejected for this scope because it adds a second supply-chain pipeline and does not replace Trivy configuration scanning. It may be reconsidered if SBOM-first verification becomes a project requirement.

### Scan the final runtime image built by the supported constructor

The workflow shall build the same final runtime target and reviewed inventory path used by developers, with a unique ephemeral tag. It shall not replace constructor rendering with a hand-written `docker build` vector. Trivy is external verification tooling: it shall not be added to the reviewed inventory, installed in the resulting image, or executed by starting the project's runtime container.

The pinned Trivy scanner shall run separately from the image under test. Scanner access to the image shall follow the least-privilege mechanism proven in Phase 0: prefer exporting the built image to an archive and mounting that archive read-only into the scanner container. Direct access to the local Docker image through the daemon is an alternative only if Phase 0 demonstrates that archive scanning is impractical and records the resulting Docker-socket risk. Repository configuration scanning likewise mounts the checkout as scanner input; it does not modify image construction inputs.

Only the final runtime image is policy-blocking initially. Builder-stage scanning is report-only or deferred because those packages are not shipped and would create a different remediation policy.

### Separate complete reporting from the blocking policy evaluation

Run/report scanning in two logical views:

1. A complete, non-blocking report containing all severities, including unfixed and allowlisted findings where the output format permits it.
2. A policy evaluation restricted to fixable `CRITICAL` vulnerabilities after valid allowlist entries are applied.

The policy-equivalent Trivy behavior is `CRITICAL` severity plus ignore-unfixed and non-zero exit on remaining findings. Full reports must still be uploaded when the policy evaluation fails.

Alternative considered: use one filtered scan as both report and gate. Rejected because it would hide the non-blocking findings explicitly requested for review.

### Treat the allowlist as expiring reviewed policy

Use a version-controlled allowlist format supported by the pinned Trivy version or a repository-owned validated translation into that format. Every exception must include:

- the precise vulnerability identifier and applicable scope;
- a non-empty rationale;
- an ISO date expiration;
- enough ownership/context to support review.

A preflight validator shall reject malformed, duplicate, over-broad, or expired entries before scanning. Allowlisted findings remain visible in the complete report even though they do not block policy evaluation. Wildcard suppression and indefinite exceptions are prohibited.

### Start with manual GitHub execution

Add a `workflow_dispatch` workflow with least-privilege token permissions, bounded timeout, concurrency control, unique image names, cleanup, scanner/database caching, and report upload guarded with `if: always()`. Its summary shall distinguish scanner/tool failure, image-build failure, policy failure, and a successful scan with non-blocking findings.

Alternative considered: enable `push`, `pull_request`, or a schedule immediately. Rejected until Phase 0 establishes duration, stability, cache behavior, and a manageable baseline.

## Risks / Trade-offs

- [The vulnerability database changes without repository changes] → Preserve database metadata in reports, cache downloads, and treat findings as time-dependent evidence rather than reproducible build output.
- [A fixable critical appears because upstream metadata changes] → Fail visibly, still upload complete reports, and require remediation or a reviewed expiring exception.
- [The allowlist hides risk] → Validate narrow IDs/scopes, require rationale and expiry, and retain allowlisted entries in the complete report.
- [The scanner container gains excessive Docker control] → Prefer archive scanning; if daemon access is required, justify it from Phase 0 and rely on the ephemeral isolated runner.
- [Image build and scan exhaust hosted-runner disk or time] → Measure in Phase 0, prune only workflow-owned resources, and set explicit timeout/retention limits.
- [Registry or Trivy database service is unavailable] → Classify this as a tooling failure, not a clean security result, and preserve diagnostics.

## Migration Plan

1. Execute and record Phase 0 preflight evidence without enabling an automatic repository gate.
2. Fix the scanner topology, pinned versions, cache keys, permissions, formats, and resource limits from that evidence.
3. Add allowlist validation and scanner support scripts/configuration with deterministic tests where possible.
4. Add the manual workflow and verify complete reports survive build, scanner, and policy failures.
5. Run `workflow_dispatch`, review the initial baseline, and remediate or explicitly allowlist qualifying findings.

Rollback removes the manual workflow and scanner support files. No runtime data or image format migration is involved.
