# Implementation Report: configure-optional-runtime-host-access

## Phase 6 Validation Results

### 6.10 — Full test suite

**Command:**
```bash
python -m unittest discover -s tests -p 'test_*.py'
```

**Result:** 2145 tests ran, 9 environment failures, 0 regressions.

| Module | Count | Kind | Cause |
|---|---|---|---|
| `test_constructor_acceptance` | 0 | — | Fixed by updating `_make_runtime_fixture()` to copy the repository's valid `docker-constructor.toml` instead of writing a minimal `[meta]\nversion = 1\n` stub. The real inventory has no `[runtime.host-access]` — host access disabled, and passes `load_inventory` successfully. |
| `test_constructor_cache_contracts` | 1 failure | Environment | `test_insecure_permissions_rejected` — `ArtifactMaterializationError` not raised. Caused by `artifact_cache.py:787` setting blob permissions to `0o444` while the test expects `0o400`-style rejection. Fails identically at base commit `3f16e9f` (before any feature changes). Zero host-access references. |
| `test_constructor_materialization` | 8 failures | Environment | `TestProductionSymlinkHardening` (3) + `TestCorruptionRecovery` (5) — all `0o292 != 0o256` (i.e. `0o444` vs `0o400`) permissions mismatches. Same `artifact_cache.py:787` cause as above. Fails identically at base commit `3f16e9f`. Zero host-access references. |

**Regression detail:** None. The 12 verify acceptance tests that previously failed now pass after updating `_make_runtime_fixture()` to use the repository's real `docker-constructor.toml`.

**Environment failures (9 tests):** All 9 fail identically at base commit `3f16e9f` — confirmed by checking out that commit and running each individually. The failures originate from `artifact_cache.py:787` (`filesystem.set_permissions(path, 0o444)`) while tests expect `0o400`. Neither the test files nor `artifact_cache.py` were modified by this change (`git log` shows zero commits touching them).

### 6.11 — Static checks

**Commands and results:**

Python AST compile (all production modules):
```bash
/usr/bin/find docker -name '*.py' -exec python3 -c "import ast; ast.parse(open('{}').read())" \;
```
Result: All pass ✓

Python AST compile (all test modules):
```bash
/usr/bin/find tests -name '*.py' -exec python3 -c "import ast; ast.parse(open('{}').read())" \;
```
Result: All pass ✓

Shell script syntax:
```bash
for f in docker/*.sh tests/*.sh; do bash -n "$f" && echo "OK: $f"; done
```
Result: All 11 scripts pass ✓

Note: No mypy, ruff, pyright, flake8, pylint, black, or isort installed in this environment. AST parse is the available static check.

### 6.12 — Validation

**OpenSpec validation:**
```bash
openspec validate "configure-optional-runtime-host-access"
```
Result: `Change 'configure-optional-runtime-host-access' is valid` ✓

**Git diff whitespace check:**
```bash
git diff --check && git diff --cached --check
```
Result: Clean ✓

### Dependency graph (6.9)

- Build remains independent: `plan_build` / `orchestrate_build` do not reference host-access, doctor, or gateway diagnosis
- Run never invokes doctor: `orchestrate_run` does not import `orchestrate_doctor` or `diagnose_gateway`
- Verification never mutates state: `verify_runtime` is purely read-only
- Local config never overrides reviewed policy: `load_local_config` is a closed typed loader consumed independently, never merged into `Inventory`

### Scope review (6.8)

No scope expansion detected across public DTOs, CLI output, filesystem writes, environment variables, or Docker vectors. All additions map to approved artifacts.

### Scenario coverage (6.7)

All 31 spec scenarios mapped to at least one focused or acceptance assertion. Zero unmapped scenarios.

### Wiring fix (6.6)

Single integration fix: `address: str | None = None` initialization in `_resolve_verify_host_access` prevents an unbound `address` variable when the local companion exists but omits `[host-access].address`.
