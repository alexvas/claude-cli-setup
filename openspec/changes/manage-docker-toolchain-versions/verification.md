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
