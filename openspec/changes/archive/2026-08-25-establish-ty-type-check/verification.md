## Type-check baseline

The baseline was captured with `ty 0.0.73` using Python 3.14 semantics before production repairs.

| Scope | Diagnostics | Classification |
| --- | ---: | --- |
| `docker/` | 153 | Maintained production findings owned by tasks 2.1–2.4 |
| `tests/` | 726 | Dynamic unittest doubles; intentionally outside this initial gate |

Production ownership is grouped by diagnostic cause:

- **Task 2.1:** unresolved imports/references and invalid annotation forms.
- **Task 2.2:** process runner/result, filesystem, HTTP/cache, and injected collaborator contracts.
- **Task 2.3:** unvalidated CLI, TOML, JSON, and generic mapping values crossing typed boundaries.
- **Task 2.4:** optional-value flow, collection shapes, return types, and override compatibility.

The canonical gate is `scripts/check-types`. Its checked-in `pyproject.toml` configuration selects Python 3.14 and includes only `docker/`; the script selects concise output without supplying an interpreter path, allowing the active clean environment's Python installation to be discovered normally.

`.github/workflows/validation.yml` runs the same script in a fresh CI job after provisioning Python 3.14 and installing exactly `ty==0.0.73`. The workflow and its immutable action pins are covered by `tests/test_ci_validation_contracts.py`. The CI command was also reproduced locally in a fresh Python 3.14 virtual environment containing only the pinned type checker, where it completed with zero diagnostics.
