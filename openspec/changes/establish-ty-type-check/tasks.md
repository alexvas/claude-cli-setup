## 1. Establish the production type-check boundary

- [ ] 1.1 Add checked-in `ty` configuration in `pyproject.toml` and a documented local/CI entry point that consumes it, equivalent to `ty check docker --python-version 3.14 --output-format concise`; verify locally and in a clean CI container that it discovers the intended sole Python installation and checks `docker/` but not dynamic `tests/` doubles.
- [ ] 1.2 Record the baseline diagnostics by module and rule—153 under `docker/` and 726 under `tests/` with `ty 0.0.73` and Python 3.14—distinguish genuine production defects from the separately scoped test-double diagnostics, and verify every production diagnostic has an owner work group.

## 2. Repair foundational contracts

- [ ] 2.1 Correct missing imports, invalid annotation forms, and orphaned module references in production code, and verify the corresponding `unresolved-reference`, `unresolved-import`, and `invalid-type-form` diagnostics are eliminated.
- [ ] 2.2 Define or align shared structural contracts for runners/results, filesystem and HTTP/cache dependencies, and injected collaborators, and verify callers and implementations type-check without broad casts or rule ignores.
- [ ] 2.3 Narrow raw CLI, TOML, JSON, and mapping values at their boundaries before typed consumption, and verify affected constructor/rendering/effective paths retain their existing behavioral tests.
- [ ] 2.4 Resolve optional-value flow, collection shape, return, and override mismatches in production modules, and verify their focused test suites and the type check pass.

## 3. Enforce and validate the gate

- [ ] 3.1 Make the canonical production `ty` command complete with zero diagnostics and verify no `--exit-zero`, rule-wide ignore, or suppression of a maintained production diagnostic is used.
- [ ] 3.2 Add the canonical command to the project validation/CI path, with `pyproject.toml` as its configuration source of truth, and verify it uses Python 3.14 reproducibly on a clean environment.
- [ ] 3.3 Run the full project test suite and the production type-check gate, and verify both pass after all annotation and interface changes.
