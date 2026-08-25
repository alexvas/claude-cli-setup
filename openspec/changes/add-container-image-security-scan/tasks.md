## 0. Prove the workflow topology

- [ ] 0.1 Add a disposable `workflow_dispatch` preflight that records hosted-runner OS, Docker/Buildx/BuildKit versions, token permissions, disk availability, and network/registry reachability, and verify the evidence is available as a job summary and downloadable artifact.
- [ ] 0.2 Build the current final runtime image through `docker/docker-constructor.py` with a unique ephemeral tag in the preflight, and verify build duration, peak disk use, cleanup behavior, and failure diagnostics are recorded.
- [ ] 0.3 Run an immutably pinned external Trivy scanner for the configuration and final-image scans in the preflight, compare daemon access versus a read-only exported image archive, and verify the selected least-privilege topology can produce complete JSON, SARIF, and human-readable outputs without adding Trivy to the inventory or image or starting the project's runtime container.
- [ ] 0.4 Exercise cold and warm Trivy database paths, GitHub cache restore/save, registry limits, artifact retention, and scanner/tool failure handling, and verify the findings document stable cache keys, timeouts, permissions, and resource bounds for the durable workflow.
- [ ] 0.5 Record the Phase 0 decision and remove or clearly supersede disposable alternatives, and verify implementation of Phases 1–3 does not begin until the selected topology and pinned versions are documented.

## 1. Establish scanner and exception policy

- [ ] 1.1 Add the immutably pinned Trivy invocation/configuration selected in Phase 0 for repository configuration and final-runtime-image scans, and verify version output and image digest match the reviewed pin.
- [ ] 1.2 Add a version-controlled allowlist schema requiring an exact vulnerability identifier/scope, non-empty rationale, owner/context, and ISO expiration date while prohibiting wildcards and indefinite entries, and verify malformed, duplicate, over-broad, and expired fixture entries are rejected by deterministic tests.
- [ ] 1.3 Add a canonical policy-scan command that applies valid exceptions, restricts blocking findings to fixable `CRITICAL` vulnerabilities, and exits non-zero when one remains; verify fixtures or controlled scanner input cover blocking, unfixed, lower-severity, valid-exception, and expired-exception outcomes.

## 2. Produce complete security evidence

- [ ] 2.1 Add a non-blocking complete-report scan for all severities and unfixed findings without hiding allowlisted vulnerabilities, and verify machine-readable output preserves vulnerability, package, fix, severity, target, and database metadata.
- [ ] 2.2 Add human-readable summary and SARIF generation from the same scan execution contract, and verify zero findings, non-blocking findings, policy findings, and scanner failure are distinguishable.
- [ ] 2.3 Ensure report generation and upload paths remain available after image-build, scanner, or policy failure, and verify a deliberately failing policy run still retains complete diagnostics and reports.

## 3. Add the durable manual GitHub workflow

- [ ] 3.1 Replace the disposable preflight with or promote it into a manual `workflow_dispatch` security workflow using the Phase 0 runner, BuildKit, Trivy, cache, timeout, permissions, and resource decisions; verify no `push`, `pull_request`, or scheduled trigger is enabled.
- [ ] 3.2 Build the supported final runtime image through the constructor with workflow-unique naming, scan it with the separately run pinned Trivy scanner using the selected least-privilege transport, and clean only workflow-owned images/archives; verify concurrent or repeated manual runs do not collide and the scan neither installs Trivy in the image nor starts the project's runtime container.
- [ ] 3.3 Pin third-party actions and scanner images immutably, grant least-privilege GitHub token permissions, and verify the workflow does not expose a Docker control socket to the scanner unless Phase 0 explicitly justified that exception.
- [ ] 3.4 Cache Trivy vulnerability data with reviewed invalidation keys and publish bounded-retention reports under `if: always()`, and verify both cold-cache and restored-cache manual runs complete with current database metadata.
- [ ] 3.5 Populate the GitHub job summary with build status, scanner status, blocking-policy result, counts by severity/fixability, allowlist status, and artifact links, and verify tooling failure cannot appear as a clean security result.

## 4. Validate scope and rollout

- [ ] 4.1 Run the workflow against the initial image baseline, remediate any fixable non-exempt `CRITICAL` finding or add only a reviewed expiring exception, and verify the policy gate passes without suppressing the complete report.
- [ ] 4.2 Run ordinary unit tests and the Hadolint gate from `migrate-stage-six-verification`, and verify this change adds no Trivy, Docker, or GitHub dependency to normal unittest discovery.
- [ ] 4.3 Document manual invocation, prerequisites, report interpretation, remediation, allowlist review/expiry, and scanner-update procedures, and verify a maintainer can execute and interpret the workflow without repository write access beyond the explicit workflow permission model.
- [ ] 4.4 Run OpenSpec strict validation and a final `workflow_dispatch` execution, and verify all planning contracts, reports, policy behavior, cleanup, and retained artifacts are satisfied.
