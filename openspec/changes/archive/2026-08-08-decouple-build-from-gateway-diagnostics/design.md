## Context

The build executor currently performs a gateway probe, fails if no route is found, and persists `HOST_GATEWAY_IP` before publishing the build projection and invoking Docker. The build vector and Dockerfile do not consume gateway state. Gateway mapping is instead a runtime `docker run --add-host` concern; `doctor` already provides the explicit diagnostic and rootless-repair workflow.

## Goals / Non-Goals

**Goals:**
- Let a validated image build run without gateway probing, gateway reachability, `.env`, or operational-state mutation.
- Preserve explicit gateway diagnostics and rootless repair through `doctor`.
- Keep runtime gateway mapping behavior separate from image construction.
- Correct all README translations to show independent build and diagnostic workflows.

**Non-Goals:**
- Change gateway candidate ordering, probe implementation, or rootless override behavior.
- Remove gateway mapping from runtime launches.
- Add build-time proxy configuration or modify Dockerfile networking.

## Decisions

### Make build a build-projection-only transaction

`execute_build()` SHALL publish the validated effective build projection and invoke the rendered Docker build vector without calling gateway diagnosis or persistence. Build result types and build tests SHALL no longer model a selected/persisted gateway as a build outcome.

Alternative: make the probe warning-only. Rejected because an unnecessary probe still slows builds, can create side effects, and obscures the command boundary.

### Keep diagnosis explicit and runtime-scoped

`doctor` remains the command that probes `host.docker.internal`, reports the selected gateway, and optionally applies the rootless Docker override. Runtime launch continues to consume operational gateway configuration for its explicit `--add-host` mapping; it does not require a successful earlier build.

Alternative: automatically run `doctor` before every launch. Rejected because it would add network/container side effects to launch planning and is outside the reported build defect.

### Document separate workflows

README build examples SHALL not instruct users to diagnose or repair host gateways before building. Gateway diagnostics shall be documented as runtime troubleshooting/setup through `doctor`.

## Risks / Trade-offs

- [A user expects build to refresh `.env`] → document that build never owns gateway state and direct users to `doctor`.
- [Existing tests encode obsolete probe-before-build behavior] → replace them with assertions that gateway callbacks are not invoked during build.
- [Runtime gateway failures occur later than build] → retain the dedicated `doctor` command and its actionable diagnostics.

## Migration Plan

No migration is required. Existing `HOST_GATEWAY_IP` values remain usable by runtime launch but are no longer created or changed by builds. Rollback restores the old orchestration, though that reintroduces the erroneous build dependency.

## Open Questions

None.
