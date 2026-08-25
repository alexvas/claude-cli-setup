## Why

`docker/verify_stage_6/` is a partially deleted Compose-era verification harness: its only remaining script imports a deleted helper and invokes a deleted CLI, its README names four deleted scripts, and its inputs no longer validate. Meanwhile, Dockerfile-specific repository contracts are scattered across tests and there is no canonical generic Dockerfile lint gate.

## What Changes

- Remove the obsolete Stage 6 scripts, documentation, and stale inventory inputs rather than repairing the retired Compose workflow.
- Consolidate and complete deterministic project-specific Dockerfile contract coverage in the standard-library unittest suite.
- Add an explicit `scripts/check-dockerfile` gate that runs a pinned official Hadolint container against the repository Dockerfile.
- Keep normal `python -m unittest discover` free of Docker, network, and third-party Python dependencies; Hadolint remains a separately invoked external tooling dependency.
- Exclude image construction, runtime E2E, Trivy/CVE scanning, and GitHub Actions from this change.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- None.

This is test and verification-tooling maintenance; it does not change product requirements.

## Impact

- Removes `docker/verify_stage_6/` remnants.
- Updates Dockerfile contract tests under `tests/`.
- Adds repository-owned Hadolint policy and a canonical containerized lint command under `scripts/`.
- Does not change `docker/docker-constructor.py` behavior, inventory semantics, image contents, or the dependency-free normal unittest command.
