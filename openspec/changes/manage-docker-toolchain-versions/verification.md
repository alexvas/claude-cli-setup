# Stage 1+1A Verification: Inventory model, constraint engine, source/update metadata, entry contracts, immutability

**Date:** 2026-07-23

## Environment

- Python: 3.14.6 (CPython)
- No Docker or network access required for this stage
- `tomllib` only (stdlib 3.11+)

## Test Suite

```
Ran 228 tests in 0.196s
OK
```

| Category | Tests | Status |
|---|---|---|
| Core values + constraints (Stage 1) | 57 | ✓ |
| Source/update metadata + compat | 19 | ✓ |
| Invalid fixtures (16 total) | 16 | ✓ |
| Additional constraints (separate file) | 39 | ✓ |
| Stage 1A: constraint regression | 4 | ✓ |
| Stage 1A: Python entry contract | 8 | ✓ |
| Stage 1A: ty entry contract | 8 | ✓ |
| Stage 1A: Pi extension contract | 9 | ✓ |
| Stage 1A: Provider-field types | 11 | ✓ |
| Stage 1A: Digest regression | 8 | ✓ |
| Stage 1A: Typed access | 14 | ✓ |
| Stage 1A: Import boundary | 3 | ✓ |
| Stage 1A: Entry-specific source/provider | 8 | ✓ |
| Stage 1A: Unknown-key rejection | 6 | ✓ |
| Stage 1A: Exact version (all entries) | 23 | ✓ |
| Stage 1A: Schema-type preservation | 4 | ✓ |
| Stage 1A: Immutability | 6 | ✓ |

## Module Decomposition

| Module | Lines | Purpose |
|---|---|---|
| `docker/versioning/errors.py` | ~20 | Exception hierarchy |
| `docker/versioning/constraints.py` | ~250 | NumericVersion, Constraint parser, consistency |
| `docker/versioning/model.py` | ~230 | Frozen dataclasses, MappingProxyType, tuples |
| `docker/versioning/inventory.py` | ~870 | TOML loader, validation, unknown-key checks |
| `docker/versions.py` | ~90 | Thin re-export wrapper |

Dependency graph: `errors → constraints → model → inventory → versions.py`

## Source/Update Metadata

Every versioned entry requires `[source]` and `[update]` with typed provider-specific dataclasses:

| Entry | Source type | Update provider |
|---|---|---|
| `base.node` | `docker-registry` | `docker-registry` |
| `toolchain.rust` | `rust-channel` | `rust-channel` |
| `toolchain.uv` | `github-release` | `github-release` |
| `toolchain.python` | `uv-python` | `uv-python` |
| `toolchain.ty` | `pypi` | `pypi` |
| `rtk-prebuilt.rtk` | `github-release` | `github-release` |
| `fd-prebuilt.fd` | `github-release` | `github-release` |
| `pi-tools.pi` | `npm` | `npm` |
| `openspec-tools.openspec` | `npm` | `npm` |
| `runtime.oh-my-zsh` | `git` | `git-ref` |
| `runtime.pi-extensions.*` | `npm` | `npm` |

## Entry-Specific Enforcement

Each entry mandates exact source/update classes — generic compatibility (e.g., `pypi↔pypi` on Python) is rejected:

- `toolchain.python`: only `uv-python`, rejects `pypi` source even though `pypi↔pypi` is a valid pair
- `toolchain.ty`: only `pypi`, rejects `npm`
- `toolchain.rust`: only `rust-channel`, rejects `github-release`
- `pi-tools.pi`, `openspec-tools.openspec`: only `npm`
- `runtime.pi-extensions.*`: only `npm`
- `base.node`: only `docker-registry`
- `runtime.oh-my-zsh`: only `git`/`git-ref`

## Unknown/Misspelled Key Rejection

All known TOML tables have allowed-key registries. Extra keys (including typos like `stabel_only`) raise `InventoryError` with the misspelled key name. Coverage includes:

- Top-level: `schema`, `stages`, `runtime`
- `stages`: 7 known sub-tables (base, toolchain, rtk-prebuilt, fd-prebuilt, pi-tools, openspec-tools, runtime)
- Each stage container: registered sub-tool names (e.g., `rtk` not `rrtk`)
- Each entry: version + source + update (+ override where applicable)
- Source/update sub-tables: checked after successful type/provider validation
- Artifact platform tables: `url` + `sha256` only via `__ANY__` wildcard — all platforms validated regardless of name (catches typos like `sh256` on `linux-arm64` too)
- `runtime` top-level: registered sub-tables (catches extra keys at runtime scope)
- `runtime.pi-extensions` entries: dynamic `__ANY__` wildcard for source/update

## Exact Version Validation

Every versioned entry enforces strict exact-version syntax:

| Entry | Format | Examples rejected |
|---|---|---|
| `toolchain.rust` | X.Y.Z | `latest`, `stable`, `1.88.0-beta` |
| `toolchain.uv` | X.Y.Z | `latest`, `v0.1.0`, `^1.0.0` |
| `toolchain.python` | X.Y.Z | `3.14` (two-part) |
| `toolchain.ty` | X.Y.Z | `latest`, `v0.0.61` |
| `pi-tools.pi`, `openspec-tools.openspec` | X.Y.Z | `latest`, `^1.0.0`, `~1.6.0` |
| `rtk-prebuilt.rtk`, `fd-prebuilt.fd` | vX.Y.Z | `1.0.0` (no v), `latest`, `v1.0` |
| `runtime.pi-extensions.*` | pinned semver | `latest`, `stable`, `next`, `dev`, `canary`, `nightly` |

Pi extensions accept strict semver.org prerelease/build forms (`0.2.0-beta.1`, `1.0.0+build.1`) but reject moving tags and malformed suffixes like `-!!!`, `-`, `+`, `-01`, `-beta..1`.

## Schema Type Preservation

Wrong-type `schema` values are diagnosed with their actual type error, not rewritten as missing-key:

| Input | Error |
|---|---|
| `schema = "1"` | `expected integer, got str` |
| `schema = true` | `expected integer, got bool` |
| `schema = 1.0` | `expected integer, got float` |
| `schema` absent | `missing required top-level key` |

No error reported when the key is absent uses the "missing" wording — type mismatches preserve the `require_int` diagnostic.

## Immutability

All loaded inventory values are truly immutable:

| Container | Implementation |
|---|---|
| `RustEntry.components` | `tuple` |
| `UvEntry.artifacts` | `MappingProxyType` |
| `PrebuiltToolEntry.artifacts` | `MappingProxyType` |
| `Inventory.runtime_pi_extensions` | `MappingProxyType` |
| All entry types | `@dataclass(frozen=True)` |

## Cross-field Validation (carried forward)

- **github-release**: `source.tag` must equal `version`
- **Placeholder SHA-256**: all-same-char checksums rejected (node digest + artifact sha256)
- **Moving Rust version**: `stable`, `beta`, `nightly` rejected (now part of `_validate_rust_version`)
- **required_platforms**: each must have artifact entry
- **Rust manifest URL**: must contain the selected version
- **Artifact URL**: must contain declared version
- **Node digest**: format `sha256:<64 lowercase hex>`, placeholder detection

## Real `versions.toml`

Production inventory loads with all 7 stage entries + 3 pi extensions:
- `toolchain.python`: `3.14.6` with `uv-python/cpython` source/update + override `>=3.14.6`
- `toolchain.ty`: `0.0.61` with `pypi` source/update (`package = "ty"`)
- `runtime.pi-extensions.*`: all 3 extensions with `npm` source/update (no entry-level `package`)

## Validation

- `compileall`: ✓ clean
- `openspec validate --strict`: ✓ valid
- `python3 docker/versions.py`: ✓ exit 0
- No Docker/network in tests: ✓
- All errors contain dot-paths: ✓
- Sanitized env (`env -i`): ✓ 228 tests OK

# Stage 2 Verification: Effective configuration CLI

**Date:** 2026-07-23

## Test Suite

```
Ran 315 tests in 3.196s
OK
```
87 new tests (315 - 228 Stage 1+1A):
- `tests/test_versions_cli.py`: 49 subprocess tests
- `tests/test_version_effective.py`: 38 domain tests

| Category | Tests | Status |
|---|---|---|
| CLI: Validate | 7 | ✓ |
| CLI: Get (scalar, container, negative) | 15 | ✓ |
| CLI: Env (text, JSON, ordering, round-trip) | 9 | ✓ |
| CLI: Override (positive + negative) | 12 | ✓ |
| CLI: Shell escape unit tests | 6 | ✓ |
| Effective: Default selection | 7 | ✓ |
| Effective: Immutability | 9 | ✓ |
| Effective: Override policy | 7 | ✓ |
| Effective: Serialization | 8 | ✓ |
| Effective: Environment mapping | 7 | ✓ |

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `docker/versioning/effective.py` | ~260 | Override application, deterministic serialization, env mapping |
| `docker/versioning/cli.py` | ~210 | argparse CLI, exit-code mapping, shell escaping |
| `tests/test_versions_cli.py` | ~400 | Subprocess-level CLI tests + shell escape unit tests |
| `tests/test_version_effective.py` | ~370 | Domain-level effective config tests |

## Files Modified

| File | Change |
|---|---|
| `docker/versioning/errors.py` | +4 exception types (EffectiveConfigError, UnknownPathError, UnsupportedOverrideError, OverrideValidationError) |
| `docker/versions.py` | +`if __name__ == "__main__"` with `main()` delegation |
| `tests/test_version_stage1a.py` | `test_direct_script_execution` now passes `validate` argument |

## CLI Exit Codes

| Code | Meaning | Trigger |
|---|---|---|
| 0 | Success | validate, get, env with valid input |
| 2 | CLI usage/arguments | malformed override token, duplicate override path |
| 3 | Invalid inventory | bad TOML, missing file, unreadable file |
| 4 | Unknown get path | typo, missing field, `__class__` |
| 5 | Unsupported override | path not in SUPPORTED_OVERRIDES |
| 6 | Override policy violation | wrong format, constraint mismatch, prerelease |

## Supported Overrides

Currently only:
```
stages.toolchain.python.version
```

## Env Output Contract

Text-format `env` emits `export NAME='value'` lines, safe for direct shell evaluation:

```sh
eval "$(python3 docker/versions.py env)"
docker compose build          # sees all exported variables
sh -c 'echo $PYTHON_VERSION'  # 3.14.6
sh -c 'echo $RUST_COMPONENTS' # rustfmt clippy
```

Values are single-quote-escaped with internal `'` handled via `'\''`:
- `hello` → `'hello'`
- `rustfmt clippy` → `'rustfmt clippy'`
- `it's` → `'it'\''s'`

## Key Design Decisions

- **Shell-safe env output**: output lines are ``export NAME='value'`` form; ``eval "$(python3 docker/versions.py env)"`` produces exported variables visible to child processes (``docker compose build``, ``sh -c ...``); embedded single quotes in values are correctly escaped (e.g., ``it's`` becomes ``'it'\''s'``)
- **Duplicate override rejection**: `--override PATH=VALUE` repeated with the same `PATH` is a usage error (exit 2), not silently accepted
- **NODE_BASE_IMAGE**: derived from `node.source.registry`/`repository` + `tag` + `digest` (e.g., `docker.io/library/node:24-trixie-slim@sha256:...`), not hardcoded `node:` prefix
- **Error handling**: `tomllib.TOMLDecodeError` and `OSError` caught explicitly; no broad `except Exception` that would mask programming defects

## Verification Evidence

- **Direct script vs package import**: byte-identical stdout/stderr
- **Default Python**: exactly `3.14.6` in all outputs
- **Python override `3.14.7`**: get → `3.14.7`, env → `PYTHON_VERSION=3.14.7`, effective JSON → only `3.14.6`→`3.14.7` differs
- **Source unchanged after override**: `load_inventory` returns original `3.14.6`
- **versions.toml unchanged**: SHA-256 identical before/after
- **No Docker, no network**: all tests pass with sanitized env
- **compileall**: clean
- **openspec validate --strict**: valid
- **Deterministic ordering**: repeated runs produce byte-identical output

# Stage 3 Verification: Update discovery, caching, and security

**Date:** 2026-07-25 (updated)

## Test Suite

```
Ran 430 tests in 3.608s       (main suite, fully offline)
Ran 65 tests in 0.004s        (provider adapters)
OK
```

Total: **495 tests** (430 + 65).  180 new tests since Stage 2 (495 − 315).

### Main suite (430)

| File | Tests | Notes |
|---|---|---|
| `tests/test_version_cache.py` | 40 | Disk + memory cache, auth isolation, permissions, corrupt-entry resilience, case-insensitive headers, Accept representation isolation, nocache bypass, read-only mode |
| `tests/test_version_check_updates.py` | 23 | Offline check-updates CLI |
| `tests/test_version_constraints.py` | 63 | Constraint semantics |
| `tests/test_version_effective.py` | 38 | Effective configuration |
| `tests/test_version_inventory.py` | 61 | Inventory loading / validation (+5 cache config validation) |
| `tests/test_version_stage1a.py` | 109 | Stage 1A contracts |
| `tests/test_version_updates.py` | 16 | Coordinator + suggestions |
| `tests/test_version_versions.py` | 28 | SemanticVersion parsing |
| `tests/test_versions_cli.py` | 52 | Subprocess CLI smoke |

### Provider suite (65)

| File | Tests | Notes |
|---|---|---|
| `tests/versioning/providers/test_docker_registry.py` | 3 | Docker Registry bearer-token |
| `tests/versioning/providers/test_git.py` | 4 | Git ref resolution |
| `tests/versioning/providers/test_github.py` | 21 | GitHub Releases + SHA256SUMS + companion files + asset digest + downgrade + prefixed digest normalisation |
| `tests/versioning/providers/test_npm.py` | 12 | npm registry + downgrade prevention |
| `tests/versioning/providers/test_pypi.py` | 8 | PyPI JSON API + downgrade prevention |
| `tests/versioning/providers/test_rust.py` | 11 | Rust stable channel + metadata + tightened regex + downgrade |
| `tests/versioning/providers/test_uv_python.py` | 6 | uv python-build-standalone + downgrade prevention |

## Provider Matrix

| Provider | Fake tests | Status |
|---|---|---|
| npm | 12 | ✓ (+1 downgrade prevention) |
| pypi | 8 | ✓ (+1 downgrade prevention) |
| github-release | 21 | ✓ (+1 downgrade, +3 companion files, +3 asset digest, +3 SHA256SUMS, +3 prefixed digest) |
| rust-channel | 11 | ✓ (+1 downgrade, +3 tightened regex rejection) |
| docker-registry | 3 | ✓ |
| git-ref | 4 | ✓ |
| uv-python | 6 | ✓ (+1 downgrade prevention) |

## Checksum Resolution Priority (GitHub)

| Priority | Source | Function |
|---|---|---|
| 0. Asset digest | ``digest`` / ``sha256`` / ``content_sha256`` / ``checksum`` / ``hash`` field on matched asset (bare hex or ``sha256:<hex>`` / ``sha256=<hex>`` normalised) | ``_normalise_digest()`` → ``_extract_asset_digest()`` |
| 1. Companion file | `<asset>.sha256` / `.sha256sum` / `.sha256sum.txt` | `_resolve_asset_companion_checksum()` |
| 2. SHA256SUMS file | Release-level checksum asset download + parse | `_resolve_checksums()` |
| 3. Body text | `sha256:` tokens and checksum-line heuristics | `_extract_checksum_for_asset()` |

## Status Matrix

| Status | Test coverage |
|---|---|
| current | ✓ |
| outdated | ✓ |
| skipped | ✓ |
| unavailable | ✓ |
| incomplete | ✓ (implicit via coordinator classification) |

## Update Kinds

| Kind | Test coverage |
|---|---|
| version | ✓ |
| digest-refresh | ✓ |
| revision | ✓ |

## Exit Codes (added)

| Code | Meaning | Tested |
|---|---|---|
| 7 | Provider failure in --strict mode | ✓ (offline, injected fake transports) |
| 8 | Applicable update found in --fail-on-outdated | ✓ (offline, injected fake transports) |

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `docker/versioning/versions.py` | ~200 | SemanticVersion parsing and ordering |
| `docker/versioning/cache.py` | ~370 | Two-tier cache, auth-scoped keys, owner-only permissions, case-insensitive headers, representation-aware keys, nocache bypass, read-only mode |
| `docker/versioning/providers/__init__.py` | ~5 | Package init |
| `docker/versioning/providers/base.py` | ~100 | Transport protocols, ProviderContext, ProviderResult |
| `docker/versioning/providers/npm.py` | ~110 | npm registry provider |
| `docker/versioning/providers/pypi.py` | ~120 | PyPI provider |
| `docker/versioning/providers/github.py` | ~320 | GitHub Releases + checksum resolution pipeline |
| `docker/versioning/providers/rust.py` | ~110 | Rust stable channel provider + tightened regex |
| `docker/versioning/providers/docker_registry.py` | ~110 | Docker Registry provider |
| `docker/versioning/providers/git.py` | ~50 | Git ref provider |
| `docker/versioning/providers/uv_python.py` | ~100 | uv-managed Python provider |
| `docker/versioning/updates.py` | ~440 | Coordinator, targets, suggestions, reports |
| `tests/versioning/__init__.py` | ~1 | Test package init |
| `tests/versioning/support/__init__.py` | ~1 | Support package init |
| `tests/versioning/support/fake_http.py` | ~60 | Fake HTTP transport |
| `tests/versioning/support/fake_git.py` | ~35 | Fake Git transport |
| `tests/versioning/support/inventory_builder.py` | ~80 | Inventory builder for coordinator tests |
| `tests/versioning/support/fixtures/versions/valid-minimal.toml` | ~15 | Minimal valid TOML fixture |
| `tests/versioning/providers/test_npm.py` | ~145 | npm provider tests (injected transports) |
| `tests/versioning/providers/test_pypi.py` | ~100 | PyPI provider tests |
| `tests/versioning/providers/test_github.py` | ~280 | GitHub provider tests |
| `tests/versioning/providers/test_rust.py` | ~120 | Rust provider tests |
| `tests/versioning/providers/test_docker_registry.py` | ~85 | Docker Registry tests |
| `tests/versioning/providers/test_git.py` | ~60 | Git provider tests |
| `tests/versioning/providers/test_uv_python.py` | ~85 | uv-python provider tests |
| `tests/test_version_versions.py` | ~130 | SemanticVersion tests |
| `tests/test_version_updates.py` | ~400 | Coordinator + suggestion tests |
| `tests/test_version_cache.py` | ~620 | Cache + auth + permissions + corrupt-entry + case-insensitive + Accept + nocache + read-only tests |
| `tests/test_version_check_updates.py` | ~550 | Offline check-updates CLI tests |

## Files Modified

| File | Change |
|---|---|
| `docker/versioning/model.py` | +CacheConfig, UpdateStatus, UpdateKind, UpdateCandidate, UpdateResult, UpdateTarget |
| `docker/versioning/errors.py` | +UpdateError, ProviderUnavailableError, UnknownFilterError |
| `docker/versioning/inventory.py` | +CacheConfig validation (`_load_cache_config`), +`cache` to known top-level keys |
| `docker/versioning/cli.py` | +check-updates, +EXIT_PROVIDER_FAILURE(7), +EXIT_OUTDATED(8), +--cache-dir, +--cache-ttl, `_resolve_transports`/`_resolve_tokens` |
| `docker/versions.toml` | +`[cache]` section (defaults for dir + ttl) |
| `tests/test_versions_cli.py` | −7 network-dependent subprocess tests; 52 arg-parsing smoke tests |

## Security Properties

### Auth-scoped cache keys

`DiskCache` and `CachingHttpTransport` derive a non-secret scope from the ``Authorization``
header (**case-insensitive** per RFC 7230 § 3.2):
- No auth → scope ``"public"``
- With auth → scope ``"auth:" + sha256(token)[:16]``

Authenticated responses are never served to unauthenticated callers or callers with a
different token.  A lowercase ``authorization`` header is correctly recognised as authed
instead of being treated as public.  The ``Authorization`` header is stripped from stored
payloads so it cannot leak via disk.

### Representation-aware cache keys

Cache keys incorporate the ``Accept`` header so that different media-type requests
for the same URL do not collide:
- Absent or ``*/*`` Accept → ``"wildcard"`` (neutral token)
- Specific type(s) → ``"accept:" + sha256(normalised)[:16]``
- Comma-separated media ranges are alphabetically sorted for stable, order-independent keys

### Private file permissions

| Artifact | Mode |
|---|---|
| Cache files | ``0600`` |
| Cache directories — target and any missing ancestors | ``0700`` |
| Pre-existing parent directories | **Never chmod-ed** |
| Pre-existing **target** directory with permissive permissions | **Clamped to ``0700``** |
| Re-write of existing file | Clamps to ``0600`` |

### Credential-bearing request bypass (nocache)

Requests to Docker Registry bearer-token endpoints (``/v2/`` probe and
``{realm}?service=…&scope=…``) are made with ``nocache=True``.  The
``CachingHttpTransport`` skips both memory and disk tiers — neither
writing token-bearing responses to disk nor reading stale tokens from
a previous invocation.  ``HttpTransport.request()`` accepts ``nocache:
bool = False`` as a keyword-only argument; all implementations (cache,
fake, production) handle it transparently.

### Corrupt entry resilience

`DiskCache.get()` catches `KeyError`, `TypeError`, `JSONDecodeError`, `OSError`, `FileNotFoundError` — returns `None` instead of crashing.

### Verification

- ``test_authenticated_cache_not_served_to_public``: token-scoped response invisible without token
- ``test_different_tokens_are_isolated``: two tokens → independent cache entries
- ``test_authorization_stripped_from_stored_response``: no ``Authorization`` on disk
- ``test_lowercase_authorization_header_not_public``: lowercase ``authorization`` recognised as authed
- ``test_lowercase_authorization_isolated_from_mixed_case``: casing difference shares same scope
- ``test_different_accept_types_are_isolated``: JSON vs HTML → separate cache entries
- ``test_no_accept_and_wildcard_are_equivalent``: absent Accept and ``*/*`` share entry
- ``test_lowercase_accept_header_recognised``: lowercase ``accept`` detected as representation
- ``test_accept_sorted_normalisation``: ``a, b`` and ``b, a`` produce identical key
- ``test_cache_file_is_owner_only``: ``0600``
- ``test_cache_dir_is_owner_only``: ``0700``
- ``test_permissions_survive_second_write``: re-write clamps loose permissions
- ``test_existing_target_dir_clamped_to_0700``: pre-existing insecure dir clamped
- ``test_pre_existing_parent_not_chmodded``: parent with ``0755`` untouched by cache writes
- 4 corrupt-entry tests: missing keys, wrong types, truncated JSON, empty files
- ``test_read_only_disk_cache_writes_are_noop``: read-only mode never writes
- ``test_nocache_bypasses_both_read_and_write``: nocache skips all tiers
- ``test_nocache_does_not_read_existing_cache``: nocache ignores populated cache

## Cache Architecture

| Tier | Lookup order | Purpose |
|---|---|---|
| In-memory | 1st (fast) | Within a single invocation |
| Disk | 2nd (persistent) | Across CLI invocations via `$XDG_CACHE_HOME/pi-cli/versioning/` |

- `CachingHttpTransport(ttl=N)` auto-creates `DiskCache` at default location
- `--cache-dir PATH` CLI flag overrides directory
- `[cache]` section in `versions.toml` sets defaults (`dir`, `ttl`)
- Precedence: CLI `--cache-dir` > `[cache].dir` > XDG default
- `--no-cache` bypasses all caching
- Atomic writes via `os.replace()` (write to `.tmp` then rename)

## Centralized Cache Configuration

`[cache]` is a fully typed, strictly validated section in `versions.toml`:

```toml
[cache]
dir = "/path/to/cache"   # optional string
ttl = 3600               # optional positive int
```

- `CacheConfig` frozen dataclass in `model.py`
- `_load_cache_config()` validates types, rejects unknown keys, enforces `ttl > 0`
- Flows through `Inventory.cache` (typed pipeline, no second `tomllib.load()`)
- 5 validation tests: no-section → None, valid dir+ttl, dir-not-string, ttl≤0, unknown-key

## Downgrade Prevention

All five value providers compare upstream maximum against selected version using typed comparison:

| Provider | Comparison type | Action when upstream max < current |
|---|---|---|
| npm | `SemanticVersion` | Returns CURRENT |
| PyPI | `SemanticVersion` | Returns CURRENT |
| GitHub | `_parse_tag_semver(tag, prefix)` | Returns CURRENT |
| Rust | `NumericVersion` | Returns CURRENT |
| uv-python | `NumericVersion` | Returns CURRENT |

Parse failures fall through gracefully to original string comparison.

## Rust Version Extraction (tightened)

Regex: `^((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))(?:\s+\([^)]*\))?$`

| Input | Accepted? |
|---|---|
| `1.97.1` | ✓ |
| `1.97.1 (abcdef01 2025-06-01)` | ✓ |
| `1.97.1garbage` | ✗ no whitespace separator |
| `1.97.1-rc1` | ✗ dash suffix |
| `1.97` | ✗ two components |

## Key Architecture Decisions

- Providers receive injected transports (never call urllib/git directly in tests)
- Fake transports fail on unexpected requests — no fallback to real network
- Production transports created only during explicit `check-updates` execution
- `validate`, `get`, `env`, and import paths make zero provider requests (9 tests)
- npm URLs are percent-encoded for scoped packages (`@scope/pkg` → `@scope%2Fpkg`)
- GitHub release candidate filename matching uses deterministic basename substitution
- GitHub checksum resolution: asset digest → companion file → SHA256SUMS → body text
- Docker digest refresh is distinct from version update (`UpdateKind.DIGEST_REFRESH`)
- Git revision updates are never compared as semantic versions (`UpdateKind.REVISION`)
- `SemanticVersion`: build metadata excluded from equality/hash per semver.org
- Rust `pkg.rust.version` may include `(hash date)` suffix; only `X.Y.Z` prefix extracted
- `render_suggestions()` emits valid TOML (`[path]` table headers, parseable by `tomllib`)
- Disk cache: auth-scoped keys (case-insensitive), ``0600``/``0700`` permissions (target always clamped, pre-existing parents untouched), corrupt-entry resilience, representation-aware keys via ``Accept`` header, nocache bypass for credential-bearing endpoints, read-only mode
- ``UnknownFilterError``: raised when ``--only`` filter(s) match no target path or provider; lists known paths and providers in the error message
- ``HttpTransport.request(nocache=True)`` added to protocol; Docker Registry token requests use it to prevent token persistence
- Production HTTP transport uses ``urlopen(req, timeout=30)`` — hung providers surface as unavailable instead of blocking indefinitely
- `[cache]` section validated through typed `CacheConfig` → `Inventory.cache` pipeline
- Coordinator propagates provider exceptions without halting remaining targets
- Suggestions rendered only for OUTDATED + applicable results
- `--only` filter validates inputs — unknown filters raise `UnknownFilterError` (exit 2) with known paths and providers listed

## Import Graph Verification

- Provider adapters: no imports from CLI, updates, or `docker/versions.py`
- Domain modules (effective, inventory, constraints, model): no network calls at import time
- `validate`/`get`/`env` + module imports: zero provider requests confirmed (9 tests)
- `compileall`: clean
- `openspec validate --strict`: valid
- Direct script vs package import: byte-identical

## Non-Mutation Evidence

- `check-updates --suggest` does NOT edit `versions.toml` (byte-for-byte comparison)
- `git status --porcelain` identical before/after `--suggest`
- `git diff` identical before/after `--suggest`
- ``os.listdir(repo)`` identical before/after ``--suggest`` — no cache files, no new files
- In suggest mode, ``_resolve_transports()`` passes ``disk_cache=None`` — disk tier disabled regardless of ``[cache].dir`` or ``--cache-dir``
- No write calls in coordinator or provider code
- Inventory object immutable after loading
- Artifact suggestions contain candidate version, URL, and SHA-256 checksum

## Stage 3 Repair Rounds

1. **Rust metadata parsing** — `pkg.rust.version` may include `(hash date)` suffix; only `X.Y.Z` prefix extracted
2. **GitHub SHA256SUMS asset download** — `_resolve_checksums()` downloads and parses checksum files; authoritative over body text
3. **Valid TOML suggestions** — `[path]` table headers instead of `# comments`; validates with `tomllib`
4. **Offline check-updates tests** — 7 network subprocess tests → 23 offline tests with injected transports
5. **Non-mutation evidence** — `versions.toml` byte-for-byte + `git status` + `git diff` before/after `--suggest`
6. **Zero-request coverage** — 9 tests: `validate`, `get`×2, `env`×2, 5 module imports
7. **Downgrade prevention** — all 5 value providers compare candidate vs current with typed precedence
8. **GitHub companion checksums** — `<asset>.sha256` / `.sha256sum` companion files (3 tests)
9. **Disk cache persistence** — `DiskCache` cross-invocation via JSON files at XDG cache path (8 tests)
10. **Rust regex tightened** — rejects `1.97.1garbage`, `1.97.1-rc1`; only X.Y.Z or X.Y.Z (hash date) (3 tests)
11. **Centralized TOML cache config** — `[cache]` with typed `CacheConfig` model, no second parse (5 tests)
12. **Auth-scoped cache keys** — token-derived scope prevents cross-token leakage (3 tests)
13. **Private file permissions** — `0600` files, `0700` dirs, re-write clamps (3 tests)
14. **Corrupt entry resilience** — missing keys, wrong types, truncated JSON, empty files → None (4 tests)
15. **GitHub asset digest field** — ``_extract_asset_digest()`` checks ``digest``/``sha256``/``checksum`` fields on asset dict (3 tests)
16. **Safe ``_ensure_dir``** — only chmods directories actually created, **plus** always clamps the target directory to ``0700`` even if it pre-existed; pre-existing parents (e.g. ``/tmp``) are never altered (2 tests)
17. **Case-insensitive Authorization** — lowercase ``authorization`` header recognised as authed; same token with different casing shares scope (2 tests)
18. **Representation-aware cache keys** — ``Accept`` header incorporated into cache key; different media types fully isolated; comma-separated ranges sorted for stable keys (4 tests)
19. **Genuinely case-insensitive header lookup** — ``_casefold_get()`` iterates all Mapping keys with ``casefold()`` instead of checking only two casings (replaced 2 tests with subTest-parameterised)
20. **Prefixed asset digest normalisation** — ``sha256:<hex>`` / ``sha256=<hex>`` / ``SHA256:<hex>`` formats recognised and normalised to bare hex; whitespace-tolerant (3 tests)
21. **--suggest non-mutation** — disk cache entirely disabled in suggest mode via ``disk_cache=None``; ``DiskCache.read_only`` flag as defense-in-depth; repo file-list snapshot in non-mutation test (1 test)
22. **Docker token endpoint nocache** — bearer-token endpoint requests bypass cache; ``HttpTransport.request(nocache=True)`` skips memory+disk tiers (3 tests)
23. **Unknown --only filter rejection** — ``UnknownFilterError`` raised for filters matching nothing; lists known paths and providers; exit 2 (usage), not 3 (2 tests: unit + subprocess)
24. **Production HTTP timeout** — ``urlopen(req, timeout=30)`` prevents hung providers from blocking CLI indefinitely; OSError caught as 503

## Real `versions.toml` Verification

- Production inventory loads with all 7 stage entries + 3 pi extensions
- `python3 docker/versions.py validate` → `valid`
- Byte stability: repeated `env` runs produce identical output
- `[cache]` section accepted as known top-level key

---

# Stage 4 Verification: Build argument rendering, orchestration, and safety hardening

**Date:** 2026-07-25 (updated 2026-07-25)

## Test Suite

```
Ran 481 tests in ~4s            (test_version*.py, fully offline)
Ran 11 tests  in 0.05s          (test_build_wrapper_versions.py)
Ran 65 tests  in 0.004s         (provider adapters)
OK
```

Total: **557 tests** (481 + 11 + 65).  62 new tests in Stage 4 (33 initial + 29 from safety hardening).

### New test files

| File | Tests | Purpose |
|---|---|---|
| `tests/test_version_rendering.py` | 28 | Build argument rendering, TOML generation+round-trip, compose_command, output-path validation |
| `tests/test_version_orchestration.py` | 14 | Mocked compose subprocess orchestration + unsafe-path rejection |
| `tests/test_build_wrapper_versions.py` | 11 | build_wrapper.py version resolution, env merge, canonical override parsing, exception safety |

### Existing test file deltas

| File | Before | After | Δ | Reason |
|---|---|---|---|---|
| `tests/test_version_rendering.py` | — | 28 | +28 | New: rendering + path validation + round-trip |
| `tests/test_version_orchestration.py` | — | 14 | +14 | New: orchestration + path rejection via CLI |
| `tests/test_build_wrapper_versions.py` | — | 11 | +11 | New: integration + parse reuse + env merge + traceback safety |

## Files Created

| File | Lines | Purpose |
|---|---|---|
| `docker/versioning/rendering.py` | ~380 | Build environment rendering (`render_build_environment`, `effective_environment`), TOML serialization (scalars-before-tables), compose_command, `_validate_inventory_output`, `EffectiveInventoryOutputError` |
| `tests/test_version_rendering.py` | ~370 | Rendering unit tests + output-path validation + round-trip |
| `tests/test_version_orchestration.py` | ~330 | Mocked compose orchestration + CLI-level path rejection |
| `tests/test_build_wrapper_versions.py` | ~360 | build_wrapper integration + parse reuse + env merge + traceback safety |

## Files Modified

| File | Change |
|---|---|
| `docker/versioning/effective.py` | Removed `effective_environment()` — moved to `rendering.py` to break the `effective ↔ rendering` import cycle |
| `docker/versioning/cli.py` | +`compose` subcommand, +`_cmd_compose()`, `_cmd_env` now writes effective inventory + includes `EFFECTIVE_VERSIONS_FILE` + passes `--platform`, +`--effective-inventory-output` + `--platform` on both `env` and `compose`, catches `EffectiveInventoryOutputError` → exit 2 |
| `docker/build_wrapper.py` | +`resolve_build_inputs()` (writes effective inventory, uses canonical `_parse_overrides`, specific exception catches — no `except Exception`), +`--inventory`/`--override`/`--platform`, merge order `{**merged, **version_env, **updates}` |
| `.gitignore` | +`.docker-generated/` |

## Build Environment → Inventory Trace

| Environment Variable | Inventory Path |
|---|---|
| `NODE_BASE_IMAGE` | `stages.base.node.{source.registry,source.repository,tag,digest}` |
| `RUST_VERSION` | `stages.toolchain.rust.version` |
| `RUST_PROFILE` | `stages.toolchain.rust.profile` |
| `RUST_COMPONENTS` | `stages.toolchain.rust.components` (space-joined) |
| `UV_VERSION` | `stages.toolchain.uv.version` |
| `UV_URL` | `stages.toolchain.uv.artifacts.linux-amd64.url` |
| `UV_SHA256` | `stages.toolchain.uv.artifacts.linux-amd64.sha256` |
| `PYTHON_VERSION` | `stages.toolchain.python.version` |
| `TY_VERSION` | `stages.toolchain.ty.version` |
| `RTK_VERSION` | `stages.rtk-prebuilt.rtk.version` |
| `RTK_URL` | `stages.rtk-prebuilt.rtk.artifacts.linux-amd64.url` |
| `RTK_SHA256` | `stages.rtk-prebuilt.rtk.artifacts.linux-amd64.sha256` |
| `FD_VERSION` | `stages.fd-prebuilt.fd.version` |
| `FD_URL` | `stages.fd-prebuilt.fd.artifacts.linux-amd64.url` |
| `FD_SHA256` | `stages.fd-prebuilt.fd.artifacts.linux-amd64.sha256` |
| `PI_VERSION` | `stages.pi-tools.pi.version` |
| `OPENSPEC_VERSION` | `stages.openspec-tools.openspec.version` |
| `OH_MY_ZSH_VERSION` | `stages.runtime.oh-my-zsh.revision` |
| `PI_*_VERSION` | `runtime.pi-extensions.<name>.version` (sorted by name) |
| `EFFECTIVE_VERSIONS_FILE` | Generated path (default: `.docker-generated/versions.toml`) |

## Override Isolation

Python override (`--override stages.toolchain.python.version=3.14.7`):
- Only `PYTHON_VERSION` changes from `3.14.6` to `3.14.7`
- All other 20+ variables unchanged
- Effective inventory TOML also reflects the override

## Safety Hardening (post-initial Stage 4)

### 1. Effective inventory actually written by `build_wrapper.py`

**Problem:** `resolve_build_inputs()` exported `EFFECTIVE_VERSIONS_FILE` in the environment but never wrote the file.  Docker builds received a nonexistent build input.

**Fix:** `resolve_build_inputs()` calls `write_effective_inventory()` before returning.
- `test_writes_effective_inventory_to_disk` — verifies `.docker-generated/versions.toml` exists after resolution

### 2. Operational environment values preserved

**Problem:** The merge ``{**version_env, **updates}`` dropped all operational values from ``.env`` (API keys, custom configuration).

**Fix:** Merge order ``{**merged, **version_env, **updates}`` — ``.env`` values flow through, version keys override only same-named entries, diagnostic ``HOST_GATEWAY_IP`` wins last.
- `test_operational_env_values_preserved_in_compose_env` — verifies ``CUSTOM_API_KEY`` survives, ``PYTHON_VERSION`` overridden, ``HOST_GATEWAY_IP`` from diagnosis wins

### 3. `--effective-inventory-output` path validation

**Problem:** The output path was unvalidated — absolute paths, ``../`` traversal, and `versions.toml` overwrite were all accepted.

**Fix:** `_validate_inventory_output(repo_root, relative_path)` in `rendering.py` rejects:

| Attack vector | Rejection |
|---|---|
| Absolute path (``/etc/hacked.toml``) | ``EffectiveInventoryOutputError`` |
| Traversal (``../../../etc/hacked.toml``) | ``EffectiveInventoryOutputError`` |
| Overwrite source (``versions.toml``) | ``EffectiveInventoryOutputError`` |
| Symlink escape (leaf) | ``EffectiveInventoryOutputError`` |
| Symlink escape (intermediate directory) | ``EffectiveInventoryOutputError`` |

Called from `write_effective_inventory(effective, destination, repo_root=…, output_path=…)`.  Both entry points (``versions.py compose`` → exit 2, ``build_wrapper.py build`` → exit 2) reject unsafe paths.

Tests:
- 5 unit tests in ``TestEffectiveInventoryOutputValidation`` (valid, absolute, traversal, versions.toml, symlink)
- 3 subprocess tests in ``TestComposeOrchestration`` (absolute, traversal, versions.toml → exit 2)

### 4. Canonical override parser reused in `build_wrapper.py`

**Problem:** `cmd_build()` had an ad-hoc override parser that silently accepted duplicate paths with last-value-wins and could expose uncaught inventory exceptions as tracebacks.

**Fix:** `cmd_build()` now imports ``_parse_overrides`` from ``docker.versioning.cli`` (same parser used by ``versions.py``).  Duplicate paths → exit 2.  All `VersionConfigError` exceptions caught → clean error message, no traceback.

Tests:
- `test_duplicate_override_rejected_not_last_value_wins` — exit 2, no compose run
- `test_invalid_inventory_caught_not_traceback` — stderr contains ``error:``, no ``Traceback``

### 5. TOML serializer: scalars-before-tables ordering + full round-trip

**Problem:** The serializer processed keys alphabetically.  After writing a `[runtime.pi-extensions.pi-read]` header, the next key (`schema`) was emitted as `schema = 1` — absorbed into the preceding table instead of the top level.  The generated file failed `load_inventory()` with `schema: missing required top-level key`.

**Fix:** `_write_dict` splits keys into three groups — scalars, nested dicts (table headers), arrays — and writes each group in order.  Scalars (`schema = 1`) always appear before any `[header]`.  Additionally:
- Inline tables omit ``None`` values (TOML has no null literal — ``ttl = ""`` was rejected as non-integer)
- All-``None`` inline tables are omitted entirely

Tests:
- `test_full_load_inventory_round_trip` — writes effective inventory, reloads with `load_inventory()`, verifies `schema` at top level and version values preserved.  Passes against both minimal fixture and production `versions.toml`.

### 6. Broad `except Exception` removed from `build_wrapper.py`

**Problem:** `cmd_build()` caught ``except Exception`` around ``resolve_build_inputs()`` — programming defects (`AttributeError`, `TypeError`, `NameError`) were silently converted to ``error: …`` with exit 3 instead of producing a traceback.

**Fix:** Replaced with five specific catches in MRO order:

| Exception | Exit | Scope |
|---|---|---|
| `VersionConfigError` | 3 | Inventory validation, override policy, effective config |
| `tomllib.TOMLDecodeError` | 3 | Malformed TOML in inventory file |
| `EffectiveInventoryOutputError` | 2 | Unsafe effective inventory output path |
| `FileNotFoundError` | 3 | Missing inventory file |
| `OSError` | 3 | Filesystem errors (permissions, disk full) |

`EffectiveInventoryOutputError` extends ``ValueError`` but is caught explicitly (not via a broad ``except ValueError``) so unrelated ``ValueError`` subclasses propagate as tracebacks.

### 7. `env` command now writes effective inventory for downstream Compose

**Problem:** ``versions.py env`` excluded ``EFFECTIVE_VERSIONS_FILE`` and never wrote the generated effective inventory.  ``eval "$(python3 docker/versions.py env)" && docker compose …`` was missing the required build input, breaking the low-level Compose contract.

**Fix:** ``_cmd_env`` now mirrors ``_cmd_compose``: writes effective inventory to disk and includes ``EFFECTIVE_VERSIONS_FILE`` in the output.  Both commands use the same ``render_build_environment()`` function.  ``--effective-inventory-output`` argument added to ``env`` subcommand.

Tests:
- ``test_writes_effective_inventory_file`` — verifies ``.docker-generated/versions.toml`` exists after ``env``
- ``test_effective_versions_file_env_var`` — ``EFFECTIVE_VERSIONS_FILE`` present and points to default path
- ``test_effective_inventory_output_override`` — ``--effective-inventory-output`` changes the path
- ``test_generated_inventory_is_loadable`` — generated TOML passes ``load_inventory()`` round-trip
- ``test_override_writes_effective_inventory`` — ``--override`` reflects in both env output and generated file
- ``test_shell_roundtrip_includes_effective_versions_file`` — ``eval "$(env)" && test -f "$EFFECTIVE_VERSIONS_FILE"`` succeeds

## Key Architecture Decisions

- **Single renderer**: `env`, `compose`, and `build_wrapper.py` all use `rendering.render_build_environment()`
- **No duplicate mapping**: `build_wrapper.py` has no hardcoded version constants or parallel version table
- **TOML generation**: `write_effective_inventory()` writes atomic TOML via `tempfile.mkstemp()` + `os.replace()`
- **TOML ordering**: scalars before tables — ``schema = 1`` before ``[stages]``; inline tables omit ``None`` values
- **Compose command**: `versions.py compose -- build pi` writes effective inventory, renders environment, runs `docker compose`
- **Exit code propagation**: `subprocess.run(check=False)` returns Compose exit code verbatim
- **Priority**: `.env` operational values < resolved version values (same-name keys only) < diagnostic updates (HOST_GATEWAY_IP)
- **`.docker-generated/`**: generated effective inventory path, gitignored
- **Output path safety**: relative-only, no traversal, no symlink escapes, no `versions.toml` overwrite — validated at the single write entry point
- **Canonical parsing**: `_parse_overrides` reused; duplicate paths, empty keys, whitespace all produce consistent exit 2 in both ``versions.py`` and ``build_wrapper.py``
- **Exception safety**: `build_wrapper.py` catches only expected errors (VersionConfigError, TOMLDecodeError, EffectiveInventoryOutputError, FileNotFoundError, OSError — no `except Exception`); programming defects propagate as uncaught tracebacks
- **Acyclic modules**: `effective.py` → `errors.py` (no rendering import); `rendering.py` → `effective` + `errors` (one-way); cycle `effective ↔ rendering` broken

## Stage 4 Repair Rounds

1. **Effective inventory written** — `resolve_build_inputs` now writes `.docker-generated/versions.toml` before Compose
2. **Operational env preserved** — merge order `{**merged, **version_env, **updates}` instead of `{**version_env, **updates}`
3. **Output-path validation** — `_validate_inventory_output` rejects absolute, traversal, versions.toml, symlinks (8 tests)
4. **Canonical override parsing** — `build_wrapper.py` reuses `_parse_overrides`; duplicate rejection + exception safety (2 tests)
5. **TOML scalars-before-tables ordering** — `schema = 1` at top level; inline table `None`-omission; full `load_inventory()` round-trip (1 test)
6. **Broad `except Exception` removed** — 5 specific catches (VersionConfigError, TOMLDecodeError, EffectiveInventoryOutputError, FileNotFoundError, OSError); programming defects propagate
7. **`env` now writes effective inventory** — `EFFECTIVE_VERSIONS_FILE` included in output; ``eval "$(env)" && docker compose`` matches canonical ``compose`` contract (6 tests)
8. **Dependency cycle broken** — `effective_environment` moved from `effective.py` to `rendering.py`; `EffectiveConfigError` imported from `errors.py`; `effective.py` no longer imports `rendering`
9. **Explicit `EffectiveInventoryOutputError` catch** — `build_wrapper.py` catches the specific exception class instead of broad `ValueError`; unrelated `ValueError` subclasses propagate as tracebacks
10. **`--platform` on `env`** — `env --platform linux-arm64` produces platform-specific artifact URLs matching `compose`/`build_wrapper` (3 tests)

## Verification Evidence

- **All 557 tests pass** with sanitized environment (`env -i`)
- **No Docker daemon** contacted — all compose tests mock `subprocess.run`
- **No network** — all rendering and build_wrapper tests use in-memory inventory
- **Full round-trip** — generated effective inventory loads via `load_inventory()` without errors
- **compileall**: clean
- **git diff --check**: clean
- **openspec validate --strict**: valid
- **Low-level Compose parity**: `eval "$(env)" && docker compose …` now works identically to `compose …`
