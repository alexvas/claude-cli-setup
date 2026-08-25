## Context

See proposal.md for motivation. The direct-constructor migration deleted the shared `evidence.py`, four Stage 6 task scripts, Compose orchestration, and the CLIs the remaining `task_6_5.py` invokes. Existing tests already inspect selected Dockerfile invariants, but those assertions are scattered and do not establish a complete project-owned contract. The repository has no Python dependency manifest and its normal unittest suite uses the standard library.

## Goals / Non-Goals

**Goals:**
- Remove the obsolete Stage 6 harness and invalid fixtures as one coherent cleanup.
- Make repository-specific Dockerfile invariants deterministic standard-library tests.
- Add a reproducible generic Dockerfile lint gate without adding a Python test dependency.
- Keep Docker-dependent linting outside ordinary unittest discovery.

**Non-Goals:**
- Recreate Compose commands, the deleted evidence collector, historical Stage 6 numbering, or a Docker E2E suite.
- Build or run the project image as part of this change.
- Add Trivy, CVE policy, SBOM generation, or GitHub Actions; those belong to a separate change.
- Introduce `pyproject.toml` solely to provision a non-Python Hadolint binary.

## Decisions

### Delete rather than repair the Stage 6 harness

Remove the entire `docker/verify_stage_6/` residue, including invalid TOML inputs. It references a retired architecture and has no independently runnable component. Before deletion, map its assertions to current deterministic coverage or classify them as obsolete so the cleanup does not silently discard a relevant project contract.

Alternative considered: restore `evidence.py` and translate `compose_command()` to the current facade. Rejected because it would preserve procedural E2E machinery explicitly outside this change's static-verification scope.

### Keep project-specific contracts in standard-library unittest

Consolidate existing Dockerfile assertions and add missing cross-file contracts that a generic linter cannot know. The contract shall cover, where applicable:

- `COPY` sources and `.dockerignore` visibility;
- constructor-rendered build arguments versus Dockerfile `ARG` declarations and use;
- constructor target stages versus Dockerfile stage names;
- copied startup/install files versus `ENTRYPOINT` and supported runtime paths;
- absence of reviewed inventory and obsolete surfaces from image construction;
- project-specific trust/bootstrap ordering already required by current behavior.

Tests shall read repository files directly and require no Docker daemon, network, Hadolint binary, or third-party Python package. Existing authoritative tests should be reused or reorganized instead of duplicated.

Alternative considered: encode all policy in Hadolint rules. Rejected because Hadolint cannot understand constructor renderers, inventory boundaries, or repository migration contracts.

### Run Hadolint as a separate pinned container gate

Add a canonical executable `scripts/check-dockerfile` that runs the official Hadolint image pinned immutably, preferably by digest, with the checkout mounted read-only and the repository root as its working directory. Repository-owned Hadolint configuration and any narrowly justified ignores shall be version controlled. The script shall propagate the linter exit code and provide an actionable error when Docker is unavailable.

Canonical separation:

```text
python -m unittest discover   # standard library; no Docker
scripts/check-dockerfile      # Docker + pinned Hadolint image
```

Alternative considered: install Hadolint through `pyproject.toml`. Rejected because Hadolint is a Haskell executable, not an authoritative Python dependency; a Python wrapper adds an unnecessary supply-chain intermediary. A checked-in downloaded binary was also rejected because it requires platform/architecture bootstrap logic that the official image already supplies.

### Keep Hadolint outside unittest discovery

Do not wrap the Hadolint subprocess in a unittest or silently skip it when Docker is absent. A wrapped external tool remains an integration gate and would make test outcomes environment-dependent. The explicit script makes prerequisites and invocation visible.

## Risks / Trade-offs

- [Pinned Hadolint policy becomes stale] → Pin immutably for reproducibility and update it through reviewed dependency maintenance.
- [String-based contract tests become brittle] → Prefer narrow parsing of relevant Dockerfile instructions and semantic cross-file assertions over broad full-text snapshots.
- [Hadolint findings conflict with intentional BuildKit/project patterns] → Record minimal rule-specific exceptions with rationale; never globally suppress findings merely to make the gate green.
- [Developers run only unittest and miss lint] → Document both canonical commands and include both in the project validation checklist.

## Migration Plan

1. Classify old Stage 6 assertions as obsolete or covered by named current static contracts.
2. Consolidate and complete dependency-free Dockerfile contract tests.
3. Add pinned containerized Hadolint policy and runner.
4. Remove `docker/verify_stage_6/` and all maintained references.
5. Run the full unittest suite and Hadolint gate independently.

Rollback is a git revert; no runtime data migration is involved.
