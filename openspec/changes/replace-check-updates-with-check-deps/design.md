## Context

The current provider pipeline selects a candidate version first. The npm provider returns early when that version equals the configured version, omitting `dist.tarball` and `dist.integrity`; the coordinator therefore cannot detect current-version metadata drift. Result DTOs also model one update status rather than several simultaneous reconciliation findings. The public facade, reports, suggestions, tests, and documentation consistently expose `check-updates`.

Runtime extension catalogs intentionally support non-default versions for reviewed overrides, but validation currently cannot distinguish reachable rollback entries from dead catalog entries. Validation must remain offline.

## Goals / Non-Goals

**Goals:**
- Reconcile every selected managed dependency's version and provider-verifiable metadata in one explicit operation.
- Preserve all discovered conditions while providing one deterministic primary status.
- Correct current-version npm metadata through the existing non-mutating whole-block suggestion model.
- Prohibit npm registry credentials and allow only bounded same-origin HTTPS metadata redirects.
- Add actionable offline warnings without rejecting legitimate override alternatives.

**Non-Goals:**
- Dependency vulnerability, license, unrelated project graph, source-code dependency analysis, lockfile ownership, or image-owned managed-extension lifecycle changes.
- Automatic inventory mutation.
- Backward compatibility for the removed command name or result status vocabulary.
- Network access from `validate`.

## Decisions

### Separate provider observations from reconciliation classification

Providers will return authoritative observations for both the selected dependency and any eligible newer candidate. For npm extensions this means reading exact selected-version `dist` metadata even when no version update exists. The coordinator will compare observations with reviewed inventory and emit typed findings before selecting a primary status.

Alternative: add an npm-only special case after ordinary update classification. Rejected because SHA-256 and image digest mismatches need the same status model and because it would continue losing simultaneous conditions.

### Represent one primary status plus ordered findings

Each result will retain a primary status for compact reporting and exit policy, plus deterministic typed findings for complete diagnostics. Severity is `integrity-mismatch`, `metadata-drift`, `incomplete`, `update-available`, `current`; inability to establish authority yields primary `unavailable`, while already-known local findings remain attached. Integrity kinds distinguish `npm-integrity`, `artifact-sha256`, and `image-digest`.

Alternative: emit multiple rows per dependency. Rejected because it destabilizes target ordering, suggestions, and compact output and obscures the dependency-level outcome.

### Protect Constructor metadata providers with explicit authority policies

Constructor-owned metadata providers use a common explicit transport boundary: each provider supplies an exact initial HTTPS URL and a normalized allowed origin (or a separately reviewed closed origin set), receives sanitized credential-free inputs, disables automatic redirects, and validates every redirect target before sending the next request. The transport rejects malformed or unsupported URLs, userinfo, HTTPS downgrade, disallowed origins, and hop-limit exhaustion, and never caches a rejected redirect as successful metadata. Provider-specific authority remains explicit rather than inferred from this common mechanism.

The artifact-backed npm provider derives its initial metadata endpoint from the validated reviewed tarball URL and uses that endpoint's normalized origin as its redirect boundary. It reconciles selected version plus schema-declared tarball URL and SRI. The managed-root version provider instead fixes its initial authority to `https://registry.npmjs.org/`, uses `https://registry.npmjs.org:443` as its only allowed origin, and compares only exact roots with latest eligible stable versions. It never inherits scope registry mappings, invokes the artifact-backed provider, requests tarball metadata, or reads closure data. The artifact-backed npm path retains its npm credential/configuration safe-identity detection, warning, and sanitization contract. The managed-root path instead uses structural non-ingress: its provider/transport boundary accepts only explicit allowlisted request inputs and receives no npm environment/configuration state, ambient HTTP authentication, `.netrc`, or cookie jar; it constructs no authorization or cookie headers, and optional proxy/CA inputs enter only through separately validated credential-free policy. Ambient npm state is neither inspected nor warned about by a root-only metadata check.

This Constructor HTTP transport is used only by explicit metadata providers. Its authority and redirect guarantees apply only to requests issued through that provider boundary and make no claim about networking performed by unrelated external tools.

### Treat exact selected-version metadata as authoritative independently of latest-version selection

Npm discovery will derive an HTTPS registry base from the validated selected artifact URL using the known package identity. A URL is eligible only when it has no userinfo, query, or fragment and its canonical path matches `/(<prefix>/)*<name>/-/<leaf>.tgz` for an unscoped package or `/(<prefix>/)*@<scope>/<name>/-/<leaf>.tgz` for a scoped package, where the registry prefix contains zero or more non-empty segments and the tarball leaf is non-empty. Empty or dot segments, percent-encoded separators or package structure, non-canonical package segments, malformed suffixes, and paths admitting no exact package-aware match are rejected rather than guessed. Removing the exact terminal package/tarball suffix yields the registry base, including its complete path prefix. The metadata endpoint is then deterministically `<base>/<name>` for an unscoped package or `<base>/@<scope>%2F<name>` for a scoped package.

The provider passes both that complete metadata URL and its normalized scheme/host/effective-port origin to the transport boundary: the base path identifies the registry endpoint, while the origin is only the redirect-security boundary. The provider inspects both selected-version and candidate-version records.

Before cache or provider activity, `check-deps` detects credential/configuration entities by safe identity only. Environment matching is case-insensitive and includes `NPM_TOKEN`, `NODE_AUTH_TOKEN`, `NPM_CONFIG_USERCONFIG`, and every `NPM_CONFIG_*` name whose normalized npm key denotes `_auth`, `_authToken`, `username`, `_password`, `password`, `otp`, `certfile`, or `keyfile`, including registry- or scope-qualified forms. It detects conventional project, user, and global npm config files by existence at their predetermined paths. `NPM_CONFIG_USERCONFIG` is detected and reported only by variable name: `check-deps` never reads its value and does not discover, test, or report the explicitly selected path. It never reads matching credential environment values or npm config bytes. When any entities are present, it emits a warning listing only their safe variable names or predetermined config paths, states that they are ignored, removes matching variables from the provider/transport environment, does not load any npm config, and continues credential-free. For `NPM_CONFIG_USERCONFIG`, the warning states that the variable and the config it selects are ignored without naming that unknown path. No value, file content, encoded secret, or secret-derived data enters diagnostics, cache identity, provider state, or requests. A pre-network gate verifies sanitization is complete; registry authority remains derived only from the reviewed tarball URL. Authenticated registries are therefore unavailable to this operation.

Npm metadata requests are credential-free and may follow only bounded same-origin HTTPS redirects. The production transport disables automatic redirects, validates each Location before sending the next request, and rejects every cross-origin redirect, HTTPS downgrade, malformed/unsupported or userinfo-bearing URL, and hop-limit excess. Cache identity is the URL actually requested; redirect-policy failures never create successful metadata cache entries.

Alternative: always query `registry.npmjs.org`. Rejected because the reviewed URL defines which registry published the artifact and private registries must not be silently compared with the public registry.

### Build suggestions from a reconciliation plan

Suggestion overlay will consume findings, not only version-outdated results. A metadata-only npm correction will keep `version` unchanged while replacing `url` and `integrity` together from one exact upstream version record. When a newer applicable version exists, the complete block will move directly to that version and its authoritative metadata while retaining the selected-version drift finding in diagnostics.

Alternative: suggest repairing the old version before suggesting the update. Rejected because it creates two manual edits and leaves the reviewed block behind the selected candidate.

### Keep offline reachability warnings in inventory validation

After parsing an extension and its override policy, validation will classify each artifact key as default, override-reachable, or unreachable. Only unreachable keys produce warnings. Warnings flow through validation presentation separately from fatal inventory errors and do not affect success.

Alternative: require exactly one artifact per extension. Rejected because reviewed rollback and compatibility overrides are intentional capabilities.

### Replace the public command atomically

Parser registration, help, docs, automation, tests, and examples will move from `check-updates` to `check-deps` in one change. No alias or tailored unknown-command hint will remain. Internal names may be migrated where they encode update-only semantics, while provider abstractions that remain accurate need not be renamed mechanically.

## Risks / Trade-offs

- [More upstream requests for selected-version metadata] → Reuse each registry response for selected and candidate records and preserve transport caching/revalidation behavior.
- [Registry URL derivation could discard a path prefix, misread encoded structure, target an authenticated registry, or accept a redirected authority] → Require the closed package-aware tarball grammar, preserve the derived base path, reject ambiguous or non-canonical paths, detect credential environment variables by safe name and conventional npm config files by predetermined path, treat `NPM_CONFIG_USERCONFIG` only as a named ignored variable without discovering its selected path, ignore all detected entities without reading values or contents, sanitize before network access, never send npm credentials, and reject unsafe redirects before their request is sent.
- [Breaking CLI and JSON status consumers] → Update all repository-owned callers and document the new canonical contract; no compatibility layer is promised.
- [Warnings could become noisy for broad override catalogs] → Warn only when policy proves a version unreachable, not merely because it is non-default.
- [One primary status can hide secondary conditions in compact output] → Preserve all findings in `Details:`, detailed mode, and JSON.

## Migration Plan

1. Introduce the observation/finding DTO contract and update provider/coordinator tests.
2. Switch the facade and all repository-owned callers atomically to `check-deps`.
3. Update reports, suggestions, exit policy, validation warnings, and translated documentation.
4. Validate that `check-updates` receives ordinary unknown-command handling and that no repository-owned reference remains.

Rollback requires reverting the complete change because old and new structured status contracts are intentionally incompatible.
