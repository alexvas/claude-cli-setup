# Implementation Contract

This checklist is a binding implementation contract for this change. A checkbox may be marked complete only when its stated outcome and evidence are present. Do not combine tasks, omit a phase gate, broaden the specified scope, or start a phase before all of its dependencies are complete.

## Phase DAG

```text
Phase 1 (local-input contract)
  ├──> Phase 2 (build contract)
  └──> Phase 3 (runtime contract)
Phase 2 ──┐
          ├──> Phase 4 (documentation and end-to-end acceptance)
Phase 3 ──┘
```

Each phase follows **RED → GREEN → INTROSPECT → VALIDATE**. “RED” means add focused failing tests that express the phase contract before production implementation. “INTROSPECT” means review the completed diff against the stated phase boundaries and correct any defect found. “VALIDATE” is the phase gate; its evidence is the checked-in executable tests and reproducible validation commands, independently rerunnable by a reviewer. Do not add a self-reported implementation record as validation evidence.

## Phase 1 — Local corporate-network input contract

**Depends on:** none  
**Deliverable:** The resolved local companion has a closed, fail-closed corporate trust/proxy model; callers receive validated local settings or a path-specific CONFIG error before Docker execution. Existing no-configuration and host-access behavior is unchanged.

### RED

- [x] 1.1 Add failing unit tests for loading absent/disabled `[corporate-trust]` settings and for resolving the companion beside both the canonical inventory and a `--inventory` custom inventory.
- [x] 1.2 Add failing unit tests requiring enabled corporate trust to use only `.docker-local/corporate-ca-bundle.crt` and to reject a missing, unreadable, empty, or PEM-framing/Base64-malformed bundle with a path-specific CONFIG error before Docker execution; preserve dependency-free acceptance of complete blocks with nonempty decodable payloads.
- [x] 1.3 Add failing unit tests for `[network.proxy]`: accept only credential-free `http`, `socks5`, and `socks5h` URLs with host and explicit port; reject userinfo, fragments, unsupported schemes, missing host/port, malformed URLs, unknown keys, and invalid `no_proxy` values.
- [x] 1.4 Add failing regression tests proving a valid external proxy works while host access is disabled and that absent corporate settings preserve existing cache and host-access behavior.

### GREEN

- [x] 1.5 Extend the closed local-companion data model and loader with `[corporate-trust].enabled` and `[network.proxy]`, resolving the companion only beside the selected inventory.
- [x] 1.6 Implement dependency-free fixed-path corporate-bundle validation for enabled trust, returning path-specific CONFIG errors for every invalid bundle condition specified by task 1.2 without X.509 semantic parsing.
- [x] 1.7 Implement proxy and optional `no_proxy` validation, returning the normalized validated settings only for the URI and key set allowed by task 1.3.
- [x] 1.8 Pass validated corporate settings through the command/planning boundary without adding their values to the reviewed inventory or effective dependency projection.

### INTROSPECT

- [x] 1.9 Review the Phase 1 diff against the local-only, fixed-file, credential-free, and host-access-independence requirements; remove any arbitrary certificate-path input, credential channel, inventory serialization, or implicit host-proxy derivation.

### VALIDATE

- [x] 1.10 Provide reproducible Phase 1 validation: the focused local-config tests and `./docker/docker-constructor.py validate` must pass when independently run, and checked-in command-boundary tests must prove invalid local inputs prevent Docker invocation. No implementation report is required or accepted as evidence.

## Phase 2 — Build-time trust and proxy contract

**Depends on:** Phase 1  
**Deliverable:** Disabled builds retain their current Docker vector; enabled builds safely expose the fixed local bundle to the build context, replace system trust before network operations, and pass only configured proxy values as stage-local build arguments.

### RED

- [x] 2.1 Add failing build-vector tests proving disabled corporate settings neither require a bundle nor emit corporate proxy arguments.
- [x] 2.2 Add failing Dockerfile/build-context tests requiring the optional fixed-bundle convention to avoid a missing-`COPY` failure while keeping `.docker-local/corporate-ca-bundle.crt` untracked.
- [x] 2.3 Add failing Dockerfile tests requiring enabled bundle validation and replacement of `/etc/ssl/certs/ca-certificates.crt` before every base-stage network operation, with applicable clients using that final path.
- [x] 2.4 Add failing build-vector and Dockerfile-helper tests requiring configured proxy URLs and optional bypass lists to travel through constructor-specific build arguments, then appear under uppercase/lowercase HTTP, HTTPS, ALL_PROXY, and explicit-only NO_PROXY variables for every networked build command while overriding conflicting inherited proxy `ENV` values.
- [x] 2.5 Add failing Dockerfile tests proving constructor-specific proxy arguments are available in every networked stage, standard proxy variables are exported only for networked `RUN` commands when configured, and neither form is converted into persistent image `ENV`.

### GREEN

- [x] 2.6 Add the tracked placeholder or generated equivalent for the fixed local bundle build-context convention and update ignore rules so the actual bundle remains untracked.
- [x] 2.7 Update the Dockerfile base stage to validate and replace the system CA bundle from the fixed build-context source before networked package or installer operations, and set applicable client CA-path configuration to the final system-bundle path.
- [x] 2.8 Extend build request, orchestration, and rendering to carry Phase 1 validated corporate settings and emit constructor-specific proxy transport arguments in the deterministic order asserted by task 2.4.
- [x] 2.9 Declare constructor-specific proxy arguments in every networked Dockerfile stage and conditionally export the standard proxy-variable contract before each networked `RUN`, overriding inherited proxy values only when configured and without adding proxy values to persistent image environment metadata.

### INTROSPECT

- [x] 2.10 Review the Phase 2 diff against disabled-build compatibility, complete-replacement semantics, local-only input boundaries, deterministic vector ordering, and SOCKS best-effort semantics; correct any violation.

### VALIDATE

- [x] 2.11 Run the Phase 2 Dockerfile, build-context, and build-vector tests; inspect a rendered disabled vector and a rendered configured vector to confirm the exact absence/presence contract.

## Phase 3 — Runtime trust, proxy, and observability contract

**Depends on:** Phase 1  
**Deliverable:** Direct launches mount the current enabled bundle read-only and inject exactly the configured proxy environment contract, independently of host access; diagnostics verify that launch contract without broad environment disclosure or daemon claims.

### RED

- [x] 3.1 Add failing run-vector tests requiring an enabled fixed bundle to be mounted read-only at `/etc/ssl/certs/ca-certificates.crt`, and requiring no such mount when trust is disabled.
- [x] 3.2 Add failing run-vector tests requiring configured proxy URLs under uppercase/lowercase HTTP, HTTPS, and ALL proxy variables, with uppercase/lowercase NO_PROXY variables only when explicitly configured.
- [x] 3.3 Add failing regression tests proving external and host endpoint proxies do not require host access, do not trigger gateway diagnostics, and do not alter host-access mappings.
- [x] 3.4 Add failing runtime-verification/diagnostic tests requiring reporting of the configured trust/proxy launch contract while forbidding arbitrary environment dumps and Docker client/daemon coverage claims.

### GREEN

- [x] 3.5 Extend run planning and rendering to add the enabled fixed bundle as a read-only bind mount at the system CA bundle path.
- [x] 3.6 Extend run planning and rendering to emit the exact configured proxy environment-variable set, omitting all proxy variables when no proxy is configured and omitting both NO_PROXY forms when no bypass list is configured.
- [x] 3.7 Extend runtime verification and diagnostics to check and report only the corporate trust/proxy launch contract defined in tasks 3.5–3.6.

### INTROSPECT

- [x] 3.8 Review the Phase 3 diff against runtime projection and artifact-mount restrictions, host-access independence, restart/new-launch bundle refresh semantics, and the no-generic-environment-dump boundary; correct any violation.

### VALIDATE

- [x] 3.9 Run the Phase 3 run-vector, launcher, and runtime-verification tests; inspect configured and unconfigured rendered run vectors to confirm mounts and environment arguments exactly match the contract.

## Phase 4 — Operator documentation and integrated acceptance

**Depends on:** Phases 2 and 3  
**Deliverable:** Operators have complete local-only setup and boundary documentation, and the integrated implementation is demonstrated by automated checks plus environment-permitted build/run acceptance evidence.

### RED

- [ ] 4.1 Add failing documentation-contract tests or assertions, where the repository’s documentation test convention supports them, for the required setup, complete-bundle, proxy-policy, refresh, SOCKS, and Docker-boundary statements.
- [ ] 4.2 Add failing integrated acceptance tests covering valid configured build/run planning, disabled compatibility, custom-inventory companion resolution, bundle error handling, proxy URI rejection, explicit-only NO_PROXY, and host-access independence across the Phase 1–3 public command paths.

### GREEN

- [ ] 4.3 Update the local-companion example and operator documentation with the fixed bundle location, local-only configuration, complete-bundle replacement responsibility, rebuild requirement for build-stage trust, restart/new-launch refresh behavior, supported proxy schemes, explicit `no_proxy`, credential prohibition, and SOCKS best-effort limitation.
- [ ] 4.4 Document the explicit operator-managed boundary for Docker client/daemon proxy and trust, registry authentication, image pulls, and `FROM` resolution.
- [ ] 4.5 Implement only the production corrections needed to make the integrated acceptance tests from task 4.2 pass; do not add behavior outside the approved specs.

### INTROSPECT

- [ ] 4.6 Review the complete change diff against every delta-spec requirement and scenario; verify documentation does not over-promise daemon coverage, live reload, trust augmentation, or universal SOCKS support, then correct any mismatch.

### VALIDATE

- [ ] 4.7 Run all focused corporate-network tests and the full project test/static-check suite used by this repository; record the exact commands and passing results.
- [ ] 4.8 Run `openspec validate configure-optional-corporate-trust-and-proxy --strict` and record passing output.
- [ ] 4.9 Where Docker and the necessary network environment are available, perform and record a representative configured build plus a new-launch/restart verification; otherwise record the unavailable prerequisite and the passing automated coverage that substitutes for it.
