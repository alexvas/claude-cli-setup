## Context

The runtime image historically exposed `/home/dev/install-pi-extensions.sh` as the protected manual setup endpoint. The active direct-Docker constructor work moves package resolution, integrity verification, installation, metadata validation, ownership checks, and rtk registration into the root entrypoint plus `docker.runtime_installer`. The shell script therefore becomes a compatibility-only delegate, while the main runtime specification, README variants, verification scripts, and evidence tooling still treat its image path as a supported contract.

This removal crosses image assembly, runtime verification, documentation, tests, and the main OpenSpec contract. It should be applied only after the protected entrypoint installer is complete and validated.

## Goals / Non-Goals

**Goals:**

- Remove the shell wrapper from the repository and runtime image.
- Make constructor-managed entrypoint installation the only supported extension setup workflow.
- Preserve integrity verification, idempotency, mounted-home protection, ownership ordering, rtk registration, and telemetry disablement.
- Remove all current-contract references that require or recommend `/home/dev/install-pi-extensions.sh`.
- Keep `docker/docker-constructor.py` as the sole public constructor facade.

**Non-Goals:**

- Changing runtime projection fields, artifact selection, package versions, or integrity policy.
- Exposing `docker.runtime_installer` as a new public host CLI.
- Removing historical references from archived OpenSpec changes.
- Redesigning runtime verification beyond replacing wrapper-specific checks.

## Decisions

### Remove the endpoint rather than retain a compatibility shim

Delete `docker/install-pi-extensions.sh` and its Dockerfile `COPY`/mode setup. A no-logic image endpoint adds maintenance and contract surface without providing isolation or behavior. The breaking removal is made explicit in the proposal and delta spec.

Alternative: retain the one-line wrapper indefinitely. Rejected because it perpetuates the manual setup workflow and forces image, documentation, and verification support for a redundant endpoint.

### Treat constructor-managed entrypoint setup as the supported migration target

User documentation SHALL direct users to `docker/docker-constructor.py run`, which mounts the narrow runtime projection and Pi home and lets the entrypoint install before final privilege drop. Direct `python3 -m docker.runtime_installer` invocation remains available for internal tests and diagnostics but is not promoted as a second public constructor interface.

Alternative: document direct module invocation as the replacement public command. Rejected because it would undermine the sole-facade contract and requires container-internal path/environment knowledge.

### Move verification to behavior and module boundaries

Runtime verification and evidence generation SHALL validate automatic entrypoint installation, resulting package metadata, ownership, rtk registration, and absence of the legacy image path. Source-contract tests SHALL inspect the Python installer and entrypoint rather than shell-wrapper text.

Alternative: replace the script check with only a file-absence assertion. Rejected because absence alone does not prove the replacement workflow remains functional.

### Preserve historical records

Archived change artifacts remain unchanged. Current main specs, active change artifacts where relevant, maintained READMEs, executable verification, fixture comments, and tests are updated so live guidance no longer names the removed endpoint.

## Risks / Trade-offs

- [External automation invokes the old image path] → Mark the removal as breaking and document constructor-managed `run` as the migration path.
- [Removing wrapper checks weakens runtime coverage] → Replace them with entrypoint/module behavior checks and post-start metadata/ownership assertions.
- [Implementation races the active direct-Docker change] → Apply only after its protected installer and entrypoint integration are complete, then rebase expectations on the final implementation.
- [Stale live references preserve a phantom contract] → Search maintained code, docs, tests, current specs, and non-archived fixtures for both repository and image paths before completion.
