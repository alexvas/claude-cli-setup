# Binding implementation contract

Completion of this change requires every checkbox below to be satisfied in order. A task is complete only when its stated observable result exists; an equivalent-looking implementation that omits an assertion, boundary, error path, or deliverable does not satisfy the task. Each phase follows **RED → GREEN → INTROSPECT → VALIDATE**. Do not begin GREEN before its RED tests fail for the intended reason, and do not begin a dependent phase before all prerequisite phases validate.

## Phase DAG

```text
Phase 1: typed reviewed/local configuration
   ├──> Phase 2: conditional direct-Docker launch
   └──> Phase 3: mode-aware doctor
             │
Phase 2 ─────┴──> Phase 4: conditional runtime verification
Phases 1–4 ─────> Phase 5: migration and documentation
Phase 5 ────────> Phase 6: integrated acceptance
```

- Phase 1 has no prerequisite.
- Phase 2 depends only on Phase 1.
- Phase 3 depends only on Phase 1.
- Phase 4 depends only on Phases 2 and 3.
- Phase 5 depends only on Phases 1 through 4.
- Phase 6 depends only on Phase 5 and therefore transitively on all earlier phases.

## 1. Typed reviewed and local configuration

**Prerequisites:** none.

**Deliverables:** immutable reviewed host-access policy; closed local companion containing only `[host-access].address` and `[cache].dir`; canonical/custom companion path resolution; reviewed `cache.dir` migration error; reviewed `cache.ttl` retention; XDG cache fallback; projection exclusion guarantees.

### RED

- [x] 1.1 Add failing inventory tests proving an absent `[runtime.host-access]` defaults to disabled and `enabled = false` rejects `mode` and `proxy-port`.
- [x] 1.2 Add failing inventory tests proving enabled host access requires exactly `docker-gateway` or `external-address` and accepts only integer proxy ports from 1 through 65535.
- [x] 1.3 Add failing local-config tests proving `docker-constructor.toml` resolves `docker-constructor.local.toml` and `/path/custom.toml` resolves `/path/custom.local.toml` without repository fallback.
- [x] 1.4 Add failing local-config tests proving the closed schema accepts only `[host-access].address` and `[cache].dir` and rejects malformed TOML, unknown keys, non-string cache paths, and invalid addresses.
- [x] 1.5 Add failing cache tests proving reviewed `cache.dir` is rejected with migration guidance, local `[cache].dir` is used, reviewed `cache.ttl` remains effective, and absent local state preserves the XDG default.
- [x] 1.6 Add failing effective-projection tests proving reviewed host-access policy, local host address, local cache directory, proxy port, and companion path never enter build or runtime dependency projections.

### GREEN

- [x] 1.7 Add immutable model types for host-access enablement, mode, optional proxy port, local host address, and local cache directory.
- [x] 1.8 Extend reviewed inventory parsing with the closed optional `[runtime.host-access]` schema and path-specific validation errors required by tasks 1.1–1.2.
- [x] 1.9 Implement canonical and custom local-companion path resolution required by task 1.3.
- [x] 1.10 Implement strict local TOML loading for the two allowed local fields and errors required by task 1.4.
- [x] 1.11 Move cache-directory resolution to local `[cache].dir`, retain reviewed `cache.ttl`, and preserve the XDG fallback required by task 1.5.
- [x] 1.12 Remove reviewed `cache.dir` from accepted inventory fields and emit the migration error required by task 1.5.
- [x] 1.13 Update effective configuration and serialization boundaries until all projection-exclusion assertions from task 1.6 pass.

### INTROSPECT

- [x] 1.14 Inspect every reader of `Inventory`, `RuntimeInventory`, `CacheConfig`, and effective projections; record through assertions or type boundaries that no consumer treats the local companion as a generic inventory overlay.
- [x] 1.15 Search maintained production code for direct parsing of local TOML, reviewed `cache.dir`, and duplicated companion-path derivation; consolidate each concern behind its single typed boundary.

### VALIDATE

- [x] 1.16 Run the focused inventory, model, immutable DTO, cache, effective projection, serialization, semantic-source, and custom-inventory test modules and fix all failures.
- [x] 1.17 Run project static checks applicable to the changed configuration modules and confirm the Phase 1 deliverables compile and validate without Docker or network access.

## 2. Conditional direct-Docker launch

**Prerequisites:** Phase 1 validated.

**Deliverables:** disabled-by-default run vector; Docker-gateway and external-address vectors using one hostname; `HOST_ACCESS_ADDRESS`; optional `HOST_PROXY_PORT`; validation before artifact/network/Docker effects; policy-aware dry-run.

### RED

- [x] 2.1 Add failing renderer tests proving disabled host access emits no `--add-host`, `HOST_ACCESS_ADDRESS`, or `HOST_PROXY_PORT` arguments.
- [x] 2.2 Add failing renderer tests proving Docker-gateway mode emits exactly one `host.docker.internal:<address>` mapping and one matching `HOST_ACCESS_ADDRESS` variable.
- [x] 2.3 Add failing renderer tests proving external-address mode supports validated IPv4 and IPv6 mappings and rejects `host-gateway` as an external address.
- [x] 2.4 Add failing renderer tests proving a configured proxy port emits only `HOST_PROXY_PORT=<port>` and does not synthesize any proxy URL or standard proxy variable.
- [x] 2.5 Add failing launcher tests proving missing or malformed enabled-mode local state fails before cache download, artifact publication, projection creation, container inspection, or Docker execution.
- [x] 2.6 Add failing dry-run tests proving host-access arguments are complete when enabled, absent when disabled, and local state remains read-only.

### GREEN

- [x] 2.7 Replace unconditional gateway fields in run request/render DTOs with typed optional host-access inputs derived from Phase 1 policy and local state.
- [x] 2.8 Resolve and validate enabled host-access state at the start of run planning before any side-effect boundary.
- [x] 2.9 Make run-vector rendering omit host-access arguments when disabled and emit the exact mapping and address variable required by tasks 2.1–2.3 when enabled.
- [x] 2.10 Add conditional `HOST_PROXY_PORT` rendering without proxy URL derivation as required by task 2.4.
- [x] 2.11 Propagate the same policy-aware host-access inputs through dry-run and real execution paths until tasks 2.5–2.6 pass.

### INTROSPECT

- [x] 2.12 Inspect all constructors of `RunRequest` and `RunRenderInputs`; remove obsolete defaults that can silently re-enable host mapping.
- [x] 2.13 Inspect the rendered Docker environment surface and prove no `.env`, `--env-file`, `PI_PROXY_URL`, `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` coupling was introduced.

### VALIDATE

- [x] 2.14 Run focused rendering, launcher, facade-run, dry-run, artifact-side-effect-order, IPv4, IPv6, and custom-inventory tests and fix all failures.
- [x] 2.15 Run static checks for launcher and rendering modules and confirm every Phase 2 vector is deterministic and shell-free.

## 3. Mode-aware doctor and atomic local persistence

**Prerequisites:** Phase 1 validated.

**Deliverables:** Docker-gateway-only probing and rootless repair; atomic local address persistence; preserved prior state on failure; no probe, repair, or mutation for disabled and external-address modes; updated helper-script ownership.

### RED

- [x] 3.1 Add failing doctor tests proving disabled host access performs no gateway probe, rootless planning, repair, or local write.
- [x] 3.2 Add failing doctor tests proving external-address mode preserves the user address and performs no gateway probe, rootless planning, repair, or local write.
- [x] 3.3 Add failing doctor tests proving Docker-gateway mode diagnoses candidates and atomically writes the successful concrete address to `[host-access].address` in the resolved companion.
- [x] 3.4 Add failing persistence tests proving successful doctor updates preserve recognized `[cache].dir` and never add unknown or reviewed-policy fields.
- [x] 3.5 Add failing failure-path tests proving diagnosis, repair, serialization, and atomic-rename failures leave the previous local file byte-for-byte intact.
- [x] 3.6 Add failing consent tests proving rootless override application remains explicit and cannot be implied by diagnosis, `--yes`, or enabled host access alone.

### GREEN

- [x] 3.7 Make doctor load reviewed host-access mode and dispatch disabled, external-address, and Docker-gateway behavior required by tasks 3.1–3.3.
- [x] 3.8 Replace `.env` gateway persistence with an atomic typed local-companion update that preserves `[cache].dir` as required by task 3.4.
- [x] 3.9 Preserve prior local bytes across every failure boundary required by task 3.5.
- [x] 3.10 Retain explicit rootless repair consent and post-repair re-diagnosis required by task 3.6.
- [x] 3.11 Update `docker/apply-rootless-port-forward.sh` to invoke only the supported Docker-gateway doctor workflow.

### INTROSPECT

- [x] 3.12 Inspect networking and doctor call graphs; prove builds, ordinary runs, disabled mode, and external-address mode cannot reach gateway probe, persistence, or systemd mutation boundaries.
- [x] 3.13 Inspect local update code for symlink, temporary-file, unknown-key, and partial-write hazards and add a focused regression assertion for each reachable hazard.

### VALIDATE

- [x] 3.14 Run focused networking, doctor orchestration, facade-doctor, local persistence, rootless repair, helper-script, and failure-injection tests and fix all failures.
- [x] 3.15 Run static and shell checks applicable to networking, orchestration, and the rootless helper and confirm Phase 3 introduces no build dependency.

## 4. Conditional runtime verification

**Prerequisites:** Phases 2 and 3 validated.

**Deliverables:** policy-derived runtime expectations; enabled mapping/address/port checks; disabled absence checks; no protocol-specific proxy connection; custom-inventory local-state consistency.

### RED

- [x] 4.1 Add failing runtime-verification tests proving enabled host access requires exact `host.docker.internal` resolution and exact `HOST_ACCESS_ADDRESS` equality.
- [x] 4.2 Add failing runtime-verification tests proving configured `HOST_PROXY_PORT` must match and omitted proxy port creates no positive port requirement.
- [x] 4.3 Add failing runtime-verification tests proving disabled host access skips positive hostname resolution and fails if constructor-set `HOST_ACCESS_ADDRESS` or `HOST_PROXY_PORT` is present.
- [x] 4.4 Add failing facade verification tests proving expectations come from the selected reviewed inventory and its matching local companion, including custom inventory names.

### GREEN

- [x] 4.5 Replace unconditional expected-gateway verification inputs with typed policy-derived host-access expectations.
- [x] 4.6 Implement enabled hostname, address-variable, and optional port-variable checks required by tasks 4.1–4.2.
- [x] 4.7 Implement disabled constructor-variable absence checks and removal of the unconditional gateway failure required by task 4.3.
- [x] 4.8 Wire canonical and custom local companion resolution into facade verification as required by task 4.4.

### INTROSPECT

- [x] 4.9 Inspect every runtime check key and reporting adapter; remove stale wording that claims gateway mapping is a build result or universal runtime invariant.
- [x] 4.10 Prove through code inspection and tests that verification does not connect to the proxy port or assume SOCKS, HTTP, HTTPS, Ollama, or Pi-proxy semantics.

### VALIDATE

- [x] 4.11 Run focused runtime-verification, facade-verify, launcher-to-verifier acceptance, JSON output, and custom-inventory tests and fix all failures.
- [x] 4.12 Run static checks for verification modules and confirm Phase 4 reports deterministic policy-derived expectations without mutating local state.

## 5. Migration, semantic cleanup, and documentation

**Prerequisites:** Phases 1, 2, 3, and 4 validated.

**Deliverables:** no supported `HOST_GATEWAY_IP`/unconditional mapping path; ignored local file and tracked example; cache-dir migration guidance; equivalent README translations; synchronized semantic assertions.

### RED

- [ ] 5.1 Add failing semantic-source tests that reject maintained production references to `.env` gateway persistence, `HOST_GATEWAY_IP`, unconditional run mapping, and reviewed `cache.dir` support.
- [ ] 5.2 Add failing configuration-template tests requiring `.gitignore` to ignore `docker-constructor.local.toml` and requiring the tracked local example to contain only documented host-address and cache-directory fields.
- [ ] 5.3 Add failing documentation parity tests requiring all README translations to describe disabled default, both host-access modes, local companion naming, optional proxy port, and `cache.dir` migration equivalently.

### GREEN

- [ ] 5.4 Remove obsolete `HOST_GATEWAY_IP` readers, writers, DTO/result fields, `.env.example` entries, and unconditional gateway wording from maintained production sources.
- [ ] 5.5 Add the local companion ignore rule and tracked `docker-constructor.local.example.toml` required by task 5.2.
- [ ] 5.6 Update README.md with the opt-in host-access workflows, external-service binding caveat, neutral environment variables, doctor scope, and cache-dir migration.
- [ ] 5.7 Apply equivalent supported commands and semantics to README.en.md and README.zh.md without introducing translation-specific behavior.
- [ ] 5.8 Update maintained semantic-source assertions and module documentation to match the final policy/local-state boundary.

### INTROSPECT

- [ ] 5.9 Search all maintained non-archived sources for `HOST_GATEWAY_IP`, unconditional `host.docker.internal`, reviewed `cache.dir`, Compose gateway assumptions, and duplicated proxy URL construction; classify or remove every hit.
- [ ] 5.10 Compare README command sets, configuration keys, defaults, mode semantics, and maintenance guidance across all three translations and resolve every mismatch.

### VALIDATE

- [ ] 5.11 Run semantic-source, documentation, configuration-template, readonly-command, CLI-help, and migration tests and fix all failures.
- [ ] 5.12 Run `openspec validate configure-optional-runtime-host-access` and confirm proposal, design, delta specs, and this binding task contract remain consistent.

## 6. Integrated acceptance and release boundary

**Prerequisites:** Phase 5 validated.

**Deliverables:** end-to-end proof for disabled, Docker-gateway, external-address, proxy-port, cache migration, custom inventory, failure safety, and build isolation; clean static checks and full project tests; reviewed scope boundary.

### RED

- [ ] 6.1 Add an acceptance test that starts from absent host-access and local config and proves build and planned run require neither gateway nor local state.
- [ ] 6.2 Add an acceptance test that configures Docker-gateway mode, records a doctor-selected local address, and proves the later run and verification consume that exact address.
- [ ] 6.3 Add an acceptance test that configures external-address mode plus proxy port and proves run emits the hostname mapping, `HOST_ACCESS_ADDRESS`, and `HOST_PROXY_PORT` without invoking doctor boundaries.
- [ ] 6.4 Add an acceptance test that combines custom inventory, custom local companion, reviewed cache TTL, and local cache directory without repository-state fallback.
- [ ] 6.5 Add an acceptance failure test proving invalid local state causes no download, cache mutation, projection publication, Docker execution, systemd mutation, or reviewed-source mutation.

### GREEN

- [ ] 6.6 Make only integration-level wiring fixes needed for tasks 6.1–6.5; do not add new policy, fallback, compatibility path, or configuration source outside the approved artifacts.

### INTROSPECT

- [ ] 6.7 Review the complete implementation diff against every requirement and scenario in this change; map each scenario to at least one focused or acceptance assertion and close every unmapped scenario.
- [ ] 6.8 Review public DTOs, CLI output, filesystem writes, environment variables, and Docker vectors for scope expansion; remove any behavior not required by the proposal, design, specs, or tasks.
- [ ] 6.9 Confirm the final dependency graph respects the phase DAG: build remains independent, run never invokes doctor, verification never mutates state, and local config never overrides reviewed policy or dependencies.

### VALIDATE

- [ ] 6.10 Run the complete project test suite and fix every regression attributable to this change.
- [ ] 6.11 Run all project typecheck, lint, formatting, compile, shell, and build checks and fix every failure attributable to this change.
- [ ] 6.12 Run OpenSpec validation and `git diff --check`, then record the exact passing commands and results in the implementation report before marking the change complete.
