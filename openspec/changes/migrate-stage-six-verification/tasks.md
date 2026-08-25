## 1. Classify and remove retired Stage 6 verification

- [ ] 1.1 Inventory every assertion and input represented by the former Stage 6 scripts, classify each as obsolete or covered by a named maintained static test, and verify the review matrix has no unclassified scenario within this change's Dockerfile-static scope.
- [ ] 1.2 Remove the Stage 6 scripts, README, package marker, and invalid inputs after the coverage review, and verify no maintained source, documentation, or test references `docker/verify_stage_6` or its deleted commands.

## 2. Establish project-specific Dockerfile contracts

- [ ] 2.1 Audit existing Dockerfile assertions across the test suite, identify duplicate and missing repository invariants, and verify the resulting contract inventory covers COPY/context visibility, build arguments, target stages, startup paths, trust ordering, and prohibited legacy/baked inputs.
- [ ] 2.2 Consolidate or add standard-library Dockerfile contract tests without broad text snapshots, and verify focused tests detect representative violations while requiring no Docker daemon, network, or third-party Python package.
- [ ] 2.3 Run `python -m unittest discover -s tests -p 'test_*.py'` without Docker available and verify the complete ordinary suite remains dependency-free and passes.

## 3. Add the containerized Hadolint gate

- [ ] 3.1 Add a repository-owned Hadolint policy with only narrowly justified rule exceptions, and verify each exception includes an actionable project rationale.
- [ ] 3.2 Add executable `scripts/check-dockerfile` using an immutably pinned official Hadolint image, a read-only checkout mount, and repository-root working directory; verify it propagates lint failures and reports Docker-unavailable errors clearly.
- [ ] 3.3 Run `scripts/check-dockerfile` with Docker available and verify the canonical Dockerfile passes with no unreviewed suppression.

## 4. Validate scope boundaries

- [ ] 4.1 Document `python -m unittest discover` and `scripts/check-dockerfile` as independent validation commands, and verify documentation does not imply Hadolint is installed through Python or run by unittest.
- [ ] 4.2 Verify no image build/runtime E2E, Trivy/CVE scan, SBOM generation, or GitHub Actions implementation entered this change, and record those concerns as belonging to a separate planned change.
- [ ] 4.3 Run OpenSpec strict validation, the full unittest suite, and the Hadolint gate, and verify all three complete successfully.
