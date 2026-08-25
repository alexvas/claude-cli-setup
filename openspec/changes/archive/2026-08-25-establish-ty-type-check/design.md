## Context

See proposal.md for motivation. With Python 3.14, `ty 0.0.73` reports 879 diagnostics from an unconfigured repository-wide scan: 153 are under `docker/` and 726 are under `tests/`. The production findings include missing imports, invalid annotation forms, untyped dependency injection, raw `object` values crossing typed boundaries, optional-value access, and incompatible runner/cache interfaces. Test findings largely arise from runtime monkeypatching and spies whose test-only attributes are intentionally absent from production protocols.

## Goals / Non-Goals

**Goals:**
- Establish a zero-diagnostic production type-check gate for `docker/` under Python 3.14.
- Fix production contracts rather than disabling diagnostic categories.
- Make the checked scope and invocation reproducible in local development and CI.

**Non-Goals:**
- Require every dynamic unittest fake to be strictly typed in this change.
- Change runtime behavior merely to satisfy a type checker.
- Silence real errors with global `ty` ignores or `--exit-zero`.

## Decisions

### Define a production-only initial gate

The canonical command checks `docker/`, uses Python 3.14 semantics, emits concise diagnostics, and excludes no maintained production module. After the Stage 6 migration removes its orphan, the intended command is:

```bash
ty check docker --python-version 3.14 --output-format concise
```

The command intentionally lets `ty` discover the container's sole Python installation. Passing `--python "$(command -v python)"` is not supported by this plan: in the container that command resolves initially to a symlink, causing `ty 0.0.73` to derive `/home/dev/.local` incorrectly as the installation root. The canonical command has been verified locally with `ty 0.0.73` and Python 3.14 to scan `docker/` and report the expected 153-diagnostic production baseline; CI shall run the same command in a clean container to verify identical interpreter discovery.

The explicit `docker/` path excludes `tests/` without weakening checks on shipping code. `pyproject.toml` shall be the checked-in, authoritative `ty` configuration for the equivalent settings; local and CI invocations shall use it so neither depends on an activated environment. A separate task wrapper is not the configuration source of truth.

Alternative considered: run bare `ty check` with rule-wide ignores. Rejected because it conflates dynamically patched tests with production code and hides production defects.

### Repair type boundaries in dependency order

First repair foundational names and annotation forms; then establish shared structural contracts for process runners/results, HTTP/cache transport, filesystems, and dependency injection. Next narrow raw CLI/TOML/JSON data before typed use, and finally resolve remaining call-site mismatches and optional paths. This sequence reduces cascaded `object` diagnostics rather than suppressing them individually.

Alternative considered: add local casts or ignores to each reported line. Rejected because it preserves ambiguous interfaces and masks invalid data-flow assumptions.

### Keep dynamic tests outside this gate, with an explicit future path

`tests/` is not part of the initial `ty` gate. Test-only fake protocols and typed helpers may be introduced later, but only when they provide useful assertion safety. The project must not use blanket ignores to make a repository-wide test scan appear clean.

## Risks / Trade-offs

- [Stricter protocols expose latent runtime contract mismatches] → preserve behavioral tests and make interface changes in small tested groups.
- [Types diverge from public runtime behavior] → prefer structural Protocols and boundary narrowing over nominal rewrites.
- [Automatic interpreter discovery could vary outside the project container] → pin Python 3.14 semantics in the canonical command and run that exact command locally and in the clean CI container, where only the intended Python installation is present.

## Migration Plan

1. Add the reproducible type-check configuration and entry point in `pyproject.toml`, and record a baseline count for `docker/`.
2. Eliminate foundational and shared-interface diagnostics, then raw-data and optional-flow diagnostics.
3. Run the zero-diagnostic canonical command and the existing test suite after each group.
4. Integrate the command into CI; leave test typing as separately scoped work.

Rollback removes the type-check gate/configuration; type annotations can be reverted independently without data migration.
