# Binding Implementation Contract

This checklist is the binding implementation contract for this change. A phase is complete only when every checkbox in that phase is complete and every listed deliverable exists. Tasks SHALL be performed in RED → GREEN → INTROSPECT → VALIDATE order within each phase. A phase may depend only on earlier phases; work SHALL NOT satisfy a dependency by relying on a later phase. If later work requires changing an earlier phase's delivered contract, reopen that earlier phase and repeat its affected INTROSPECT and VALIDATE tasks before proceeding.

## 1. Reconciliation Result Contract

**Depends on:** none.

**Deliverables:** immutable result/finding DTO contract; six primary statuses; typed integrity kinds; deterministic finding order and primary-status precedence; structured serialization; aggregate exit policy.

### RED

- [ ] 1.1 RED — Add one failing model test enumerating exactly `current`, `update-available`, `metadata-drift`, `integrity-mismatch`, `incomplete`, and `unavailable`, and verify it fails because the reconciliation status contract does not exist.
- [ ] 1.2 RED — Add one failing model test enumerating exactly `npm-integrity`, `artifact-sha256`, and `image-digest`, and verify it fails because typed integrity findings do not exist.
- [ ] 1.3 RED — Add one failing serialization test for a result containing one primary status and multiple ordered findings with configured and authoritative values, and verify the missing fields cause the failure.
- [ ] 1.4 RED — Add one failing precedence test for each adjacent pair in `integrity-mismatch > metadata-drift > incomplete > update-available > current`, and verify classification does not yet satisfy the table.
- [ ] 1.5 RED — Add one failing test proving `unavailable` is primary when authority cannot be established while independently known local findings remain attached, and verify current classification loses that distinction.
- [ ] 1.6 RED — Add one failing aggregate exit-policy test proving only all-`current`/`update-available` result sets exit zero, and verify existing policy disagrees.

### GREEN

- [ ] 1.7 GREEN — Introduce the six-value reconciliation status type and verify task 1.1 passes without changing provider behavior.
- [ ] 1.8 GREEN — Introduce the typed finding and three integrity-kind values and verify task 1.2 passes.
- [ ] 1.9 GREEN — Extend the result DTO and canonical serializer with ordered findings and configured/authoritative values, and verify task 1.3 passes.
- [ ] 1.10 GREEN — Implement deterministic primary-status selection and verify tasks 1.4–1.5 pass.
- [ ] 1.11 GREEN — Implement aggregate exit classification over reconciliation statuses and verify task 1.6 passes.

### INTROSPECT

- [ ] 1.12 INTROSPECT — Enumerate every constructor of the old update result/status DTO and record each migration site in the phase notes or test parametrization; verify repository search finds no unclassified constructor.
- [ ] 1.13 INTROSPECT — Compare serialized fields consumed by facade, read-only service, reports, suggestions, and tests against the new DTO, and verify every consumer-required field has one authoritative owner.
- [ ] 1.14 INTROSPECT — Check status precedence against every pairwise combination of findings and verify a table-driven test covers all combinations rather than only examples.

### VALIDATE

- [ ] 1.15 VALIDATE — Run the focused model, serialization, classification, and exit-policy tests and verify all Phase 1 tests pass.
- [ ] 1.16 VALIDATE — Run static type checks for the changed DTO boundary and verify no consumer relies on an untyped compatibility fallback.

## 2. Authoritative Provider Observations

**Depends on:** Phase 1.

**Deliverables:** provider observation contract for selected and candidate values; exact selected-version artifact-backed npm metadata; fixed-public-registry managed-root version observations; explicit provider authority policies over one protected Constructor metadata transport; prohibition of npm registry credentials; bounded same-origin HTTPS redirect handling before follow; and SHA-256 and image-digest observations expressed through Phase 1 findings.

### RED

- [ ] 2.1 RED — Add one failing npm provider test proving an exact selected-version observation includes `dist.tarball` and `dist.integrity` when selected equals latest, and verify the current early return omits them.
- [ ] 2.2 RED — Add one failing npm provider test proving one registry response yields distinct selected-version and newer-candidate observations, and verify the current candidate-only contract fails.
- [ ] 2.3 RED — Add failing tests deriving public-registry metadata endpoints from reviewed unscoped and scoped tarball URLs, including canonical conversion of scoped `@scope/name` to the single metadata key `@scope%2Fname`, and verify authority is currently hard-coded.
- [ ] 2.4 RED — Add failing tests deriving metadata endpoints from validated non-default HTTPS registries with path prefixes; add rejection cases for percent-encoded tarball path structure, encoded separators, empty, dot, and duplicate-separator segments, wrong package identity, malformed `/-/<leaf>.tgz` suffixes, userinfo, queries, and fragments; and verify the provider currently drops or ambiguously interprets these distinctions.
- [ ] 2.5 RED — Add table-driven failing tests for the artifact-backed npm metadata provider covering `NPM_TOKEN`, `NODE_AUTH_TOKEN`, `NPM_CONFIG_USERCONFIG`, case variants, registry/scope-qualified auth-related `NPM_CONFIG_*`, and conventional project/user/global npm-config paths; prove its existing safe-identity warning/sanitization contract without reading values or bytes. Separately add managed-root tests proving its closed provider/transport API never receives or inspects npm environment/configuration, ambient HTTP authentication, `.netrc`, or cookies and emits no warning derived from those absent inputs.
- [ ] 2.6 RED — Add failing transport/provider tests for artifact-backed public/non-default registry requests and managed-root unscoped/scoped requests fixed to `https://registry.npmjs.org/`; verify exact initial URLs, provider-specific normalized allowed origins, a closed request-header allowlist without `Authorization`, `Proxy-Authorization`, or `Cookie`, separately validated credential-free proxy/CA inputs, same-origin redirect follow, cross-origin rejection before a second request, HTTPS-to-HTTP downgrade, validation of every redirect-chain hop, malformed, unsupported, and userinfo-bearing Locations, controlled redirect-limit exhaustion, and no successful cache entry for rejected redirects.
- [ ] 2.7 RED — Add one failing exact-version metadata test for missing `dist.tarball`, one for missing `dist.integrity`, and one for malformed integrity, and verify each produces an incomplete observation rather than current.
- [ ] 2.8 RED — Add one failing provider test mapping a changed artifact SHA-256 to `integrity-mismatch/artifact-sha256`, and verify the old digest-refresh result differs.
- [ ] 2.9 RED — Add one failing provider test mapping a changed image digest to `integrity-mismatch/image-digest`, and verify the old digest-refresh result differs.

### GREEN

- [ ] 2.10 GREEN — Add selected-value and candidate-value observations to the provider boundary and verify task 2.2 passes against the Phase 1 DTO contract.
- [ ] 2.11 GREEN — Remove the npm selected-equals-latest metadata early return and verify task 2.1 passes.
- [ ] 2.12 GREEN — Implement the closed package-aware tarball URL grammar, derive and preserve the complete HTTPS registry base path, and construct deterministic unscoped and scoped metadata endpoints from the known package identity; verify tasks 2.3–2.4 pass.
- [ ] 2.13 GREEN — Preserve safe-identity detection, warnings, and pre-cache/network sanitization for the artifact-backed npm metadata provider. Implement the managed-root provider as structural non-ingress with a closed explicit-input API that accepts no npm environment/configuration state, ambient authentication, `.netrc`, or cookies and emits no ambient npm warning; construct only allowlisted credential-free request inputs and verify task 2.5 passes.
- [ ] 2.14 GREEN — Make each Constructor metadata provider pass an exact initial HTTPS URL and normalized allowed origin into a transport with automatic redirects disabled; implement bounded explicit validation before every follow, fix the managed-root provider to `https://registry.npmjs.org:443`, reject credential-bearing request inputs, and ensure redirect-policy failures cannot be requested or cached as successful metadata; verify task 2.6 passes.
- [ ] 2.15 GREEN — Classify malformed or incomplete exact-version npm records without claiming current and verify task 2.7 passes.
- [ ] 2.16 GREEN — Emit SHA-256 and image-digest observations through the common integrity finding contract and verify tasks 2.8–2.9 pass.

### INTROSPECT

- [ ] 2.17 INTROSPECT — Inventory every provider and classify which selected-version metadata it can authoritatively verify; verify each provider explicitly returns checked, incomplete, unavailable, or not-applicable observations.
- [ ] 2.18 INTROSPECT — Inventory every process-environment, npm-config, ambient-authentication, `.netrc`, cookie, proxy/CA, and request-header ingress point plus every Constructor HTTP transport implementation and test double. Verify artifact-backed npm retains its declared safe-identity sanitization, the managed-root path has no ambient npm/auth ingress to sanitize, no Constructor metadata path follows redirects automatically, and no credential or secret-derived data reaches requests.
- [ ] 2.19 INTROSPECT — Trace each provider's initial URL and authority policy, separately computed allowed origin, every request URL and redirect hop, and cache identity; verify artifact-backed registry base paths are never reduced to origins, managed-root authority remains exactly `https://registry.npmjs.org:443`, every hop is checked before follow, and no cross-origin body can be reused as authority.

### VALIDATE

- [ ] 2.20 VALIDATE — Run focused artifact-endpoint derivation, fixed managed-root unscoped/scoped endpoints, malformed and encoded tarball paths, transport, both npm metadata providers, cache/revalidation, artifact-provider credential sanitization/warnings, root-provider structural non-ingress, redirect-policy, and acceptance tests. Use transport doubles to prove unsafe redirects cause no next request or successful cache entry. Use sentinel npm environment/config values, `.netrc`, cookies, authorization headers, and proxy credentials to prove root-provider inputs/state/cache/diagnostics/requests cannot observe them; preserve artifact-provider safe-name warning assertions; search for unclassified credential ingress paths and verify all Phase 2 tests pass.
- [ ] 2.21 VALIDATE — Run provider boundary type checks and verify every provider conforms to the Phase 2 observation contract without compatibility shims.

## 3. Reconciliation and Suggestions

**Depends on:** Phases 1 and 2.

**Deliverables:** authoritative-versus-reviewed comparison; simultaneous findings; deterministic primary classification; metadata-only and version-update reconciliation plans; complete non-mutating replacement fragments.

### RED

- [ ] 3.1 RED — Add one failing coordinator test for latest npm version with mismatching SRI and verify expected status is `integrity-mismatch/npm-integrity` rather than current.
- [ ] 3.2 RED — Add one failing coordinator test for latest npm version with only a mismatching tarball URL and verify expected status is `metadata-drift`.
- [ ] 3.3 RED — Add one failing coordinator test for simultaneous npm URL and SRI mismatches and verify both findings survive with integrity mismatch primary.
- [ ] 3.4 RED — Add one failing coordinator test for a newer candidate coexisting with selected-version metadata drift and verify both findings survive with metadata drift primary.
- [ ] 3.5 RED — Add one failing coordinator test for unavailable authority with an independently known local finding and verify unavailable is primary while the local finding remains attached.
- [ ] 3.6 RED — Add one failing suggestion test proving a metadata-only npm correction preserves the selected version and replaces URL plus integrity together.
- [ ] 3.7 RED — Add one failing suggestion test proving a newer applicable npm candidate supersedes selected-version repair in the fragment while diagnostics retain both findings.
- [ ] 3.8 RED — Add one failing replacement-block test combining multiple applicable findings owned by one block into one non-overlapping TOML fragment.
- [ ] 3.9 RED — Add one failing round-trip test proving each new fragment is accepted by the ordinary inventory loader and leaves source files unchanged.

### GREEN

- [ ] 3.10 GREEN — Implement field-by-field authoritative-versus-reviewed comparison for selected artifacts and verify tasks 3.1–3.3 pass.
- [ ] 3.11 GREEN — Aggregate provider observations into ordered findings and select the Phase 1 primary status without discarding simultaneous conditions; verify tasks 3.4–3.5 pass.
- [ ] 3.12 GREEN — Introduce a reconciliation plan consumed by suggestion generation and verify metadata-only corrections in task 3.6 pass.
- [ ] 3.13 GREEN — Prefer a complete newer-candidate replacement over repairing the old selected artifact in the fragment and verify task 3.7 passes.
- [ ] 3.14 GREEN — Overlay all applicable reconciliation-plan values once per owning reviewed block and verify task 3.8 passes.
- [ ] 3.15 GREEN — Preserve unchanged block leaves, configured platforms, visual boundaries, and non-mutating behavior and verify task 3.9 passes.

### INTROSPECT

- [ ] 3.16 INTROSPECT — Enumerate every reviewed field that each provider can correct and verify each maps to exactly one finding kind and one reconciliation-plan operation.
- [ ] 3.17 INTROSPECT — Compare text-fragment and structured-suggestion generation paths and verify they consume the same reconciliation plan without divergent candidate selection.
- [ ] 3.18 INTROSPECT — Search suggestion overlay code for assumptions that only `OUTDATED` results are applicable and verify all update-only gates are removed or deliberately retained with tests.

### VALIDATE

- [ ] 3.19 VALIDATE — Run focused coordinator, applicability, replacement-fragment, structured-suggestion, round-trip, visual-boundary, and no-mutation tests and verify all Phase 3 tests pass.
- [ ] 3.20 VALIDATE — Run property or table-driven coverage for finding precedence and block grouping across input order permutations and verify deterministic output bytes.

## 4. Offline Artifact Reachability Validation

**Depends on:** Phase 1.

**Deliverables:** offline warning model; classification of default, override-reachable, and unreachable runtime artifacts; actionable non-fatal validation rendering; no network effects.

### RED

- [ ] 4.1 RED — Add one failing validation test proving the default artifact never warns merely for being selected.
- [ ] 4.2 RED — Add one failing validation test proving a non-default version satisfying override policy does not warn.
- [ ] 4.3 RED — Add one failing validation test proving a non-default version excluded by override policy warns with extension path and exact version.
- [ ] 4.4 RED — Add one failing validation test proving multiple unreachable versions produce deterministic distinct warnings.
- [ ] 4.5 RED — Add one failing validation test proving warning-only validation exits zero.
- [ ] 4.6 RED — Add one failing effect-boundary test proving reachability validation performs no network, Docker, or subprocess operation.
- [ ] 4.7 RED — Add one failing scope test proving build-only validation does not emit runtime artifact warnings while runtime and full validation do.

### GREEN

- [ ] 4.8 GREEN — Add a non-fatal validation diagnostic boundary separate from inventory errors and verify task 4.5 passes.
- [ ] 4.9 GREEN — Classify every runtime artifact key as default, override-reachable, or unreachable using validated policy and verify tasks 4.1–4.4 pass.
- [ ] 4.10 GREEN — Integrate reachability diagnostics into runtime/full validation scopes and verify task 4.7 passes.
- [ ] 4.11 GREEN — Render actionable deterministic warnings without provider access and verify task 4.6 passes.

### INTROSPECT

- [ ] 4.12 INTROSPECT — Enumerate every override scheme and constraint boundary accepted for runtime extensions and verify reachability tests cover inclusive, exclusive, prerelease, and malformed-policy edges owned by existing validation.
- [ ] 4.13 INTROSPECT — Trace validation call paths and verify warning collection cannot import or invoke provider, transport, Docker, or mutation boundaries.
- [ ] 4.14 INTROSPECT — Compare warning ordering with canonical inventory ordering and verify duplicate artifact declarations cannot produce duplicate diagnostics.

### VALIDATE

- [ ] 4.15 VALIDATE — Run focused inventory, override-constraint, validation-scope, facade-validation, and read-only effect tests and verify all Phase 4 tests pass.
- [ ] 4.16 VALIDATE — Run acceptance coverage using the original stale-version catalog shape and verify only policy-unreachable versions warn while validation remains successful.

## 5. Public CLI and Reporting

**Depends on:** Phases 1, 2, and 3.

**Deliverables:** canonical `check-deps` command; removed `check-updates`; compact, detailed, details-section, JSON, progress, filtering, suggestion, and exit behavior over reconciliation results.

### RED

- [ ] 5.1 RED — Add one failing parser test requiring `check-deps` with the former dependency-check options and verify the command is absent.
- [ ] 5.2 RED — Add one failing parser test proving `check-updates` receives ordinary unknown-command handling with no alias or tailored migration hint.
- [ ] 5.3 RED — Add one failing compact-report test covering all six statuses in the fixed column contract and deterministic target order.
- [ ] 5.4 RED — Add one failing details-section test proving an integrity mismatch prints kind plus unabridged configured and authoritative values outside the compact table.
- [ ] 5.5 RED — Add one failing detailed-report test covering full paths, all findings, applicability, publication time, and detail text.
- [ ] 5.6 RED — Add one failing JSON test proving one primary status and all ordered typed findings are emitted identically with and without `--details`.
- [ ] 5.7 RED — Add one failing facade exit test proving update-only results exit zero while each drift, mismatch, incomplete, and unavailable status exits non-zero.
- [ ] 5.8 RED — Add one failing progress test proving interactive progress names `check-deps` targets without changing structured output.

### GREEN

- [ ] 5.9 GREEN — Replace public parser/facade registration with `check-deps` and verify tasks 5.1–5.2 pass.
- [ ] 5.10 GREEN — Adapt compact rendering to the six-status reconciliation contract and verify task 5.3 passes.
- [ ] 5.11 GREEN — Adapt details-section rendering to typed findings and unabridged comparison values and verify task 5.4 passes.
- [ ] 5.12 GREEN — Adapt detailed rendering without changing reconciliation semantics and verify task 5.5 passes.
- [ ] 5.13 GREEN — Adapt JSON serialization and suggestion envelopes to the Phase 1/3 contracts and verify task 5.6 passes.
- [ ] 5.14 GREEN — Wire aggregate reconciliation exit policy through facade and read-only service and verify task 5.7 passes.
- [ ] 5.15 GREEN — Rename interactive progress and repository-owned command dispatch paths and verify task 5.8 passes.

### INTROSPECT

- [ ] 5.16 INTROSPECT — Enumerate every facade, read-only service, TUI, filter, cache, details, JSON, suggestion, and progress path and verify each invokes one canonical reconciliation service.
- [ ] 5.17 INTROSPECT — Search executable code and tests for public `check-updates` registration or tailored migration handling and verify only explicit unknown-command assertions remain.
- [ ] 5.18 INTROSPECT — Compare compact, detailed, JSON, and suggestion outputs from identical results and verify presentation mode cannot alter findings, ordering, applicability, or exit policy.

### VALIDATE

- [ ] 5.19 VALIDATE — Run focused facade, parser, read-only service, TUI, progress, filtering, cache, report, JSON, suggestion, and exit-code tests and verify all Phase 5 tests pass.
- [ ] 5.20 VALIDATE — Run CLI acceptance tests for `check-deps`, `check-deps --details`, `check-deps --suggest`, combined options, and removed `check-updates`, and verify observable behavior matches the specs.

## 6. Repository Integration and Documentation

**Depends on:** Phases 1, 2, 3, 4, and 5.

**Deliverables:** all repository-owned integrations migrated; three README translations and CLI help aligned; no unintended old-command references; complete project green loop.

### RED

- [ ] 6.1 RED — Add or update one documentation contract test requiring `deps` to mean only dependencies declaratively managed by `docker-constructor.toml`, and verify current docs fail it.
- [ ] 6.2 RED — Add or update one documentation contract test requiring all six statuses, three integrity kinds, suggestion semantics, registry-derived network authority, and exit policy, and verify current docs fail it.
- [ ] 6.3 RED — Add one repository contract test rejecting user-facing or automation invocations of `check-updates` outside explicit historical/spec fixtures, and verify current references fail it.
- [ ] 6.4 RED — Add one end-to-end acceptance test reproducing a latest npm version with another package's syntactically valid SRI and verify the current command fails to diagnose it.
- [ ] 6.5 RED — Add one end-to-end acceptance test combining unreachable artifact warnings from `validate` with successful exit and verify current validation omits the warning.

### GREEN

- [ ] 6.6 GREEN — Update CLI help and maintained examples to define the exact `check-deps` scope and verify task 6.1 passes for those surfaces.
- [ ] 6.7 GREEN — Update README.md with reconciliation statuses, findings, suggestions, registry behavior, offline validation warnings, and exit policy and verify its documentation tests pass.
- [ ] 6.8 GREEN — Apply the same normative content to README.en.md and verify translation contract tests pass.
- [ ] 6.9 GREEN — Apply the same normative content to README.zh.md and verify translation contract tests pass.
- [ ] 6.10 GREEN — Replace repository-owned automation and supported invocation examples with `check-deps` and verify task 6.3 passes.
- [ ] 6.11 GREEN — Complete end-to-end wiring for current-version npm metadata reconciliation and verify task 6.4 passes.
- [ ] 6.12 GREEN — Complete end-to-end validation warning wiring and verify task 6.5 passes.

### INTROSPECT

- [ ] 6.13 INTROSPECT — Search all maintained code, scripts, workflows, tests, and documentation for `check-updates` and classify every remaining occurrence as explicit history/spec/rejection coverage; verify no executable or user-guidance occurrence remains.
- [ ] 6.14 INTROSPECT — Compare README.md, README.en.md, README.zh.md, CLI help, structured schema/examples, and actual status vocabulary and verify all surfaces describe the same contract.
- [ ] 6.15 INTROSPECT — Trace the original wrong-SRI scenario from registry observation through finding classification, suggestion rendering, exit code, and runtime-independent validation boundaries and verify no cache-hit or already-installed path can make `check-deps` report current.
- [ ] 6.16 INTROSPECT — Review the implementation against every requirement and scenario in this change and record one test or explicit validation command covering each scenario.

### VALIDATE

- [ ] 6.17 VALIDATE — Run all focused provider, reconciliation, suggestion, inventory, facade, reporting, documentation, and acceptance suites and verify they pass together without order dependence.
- [ ] 6.18 VALIDATE — Run project type checking and verify it passes with no ignored errors introduced by this change.
- [ ] 6.19 VALIDATE — Run project lint and formatting checks and verify they pass without suppressions introduced by this change.
- [ ] 6.20 VALIDATE — Run the complete test suite and verify all tests pass.
- [ ] 6.21 VALIDATE — Run build and repository contract checks and verify all artifacts and generated outputs are current.
- [ ] 6.22 VALIDATE — Run the configured green loop and verify its final report is fully passing before marking the change implemented.
