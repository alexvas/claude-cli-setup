# Verification — bound-pi-assembly-execution

Run Date: 2026-09-04T15:23:09Z

## Phase 1 — Reviewed Assembler Limit Policy and Identity

### Selected reviewed finite values

The standalone npm assembler now runs under one fixed reviewed policy
(`docker/npm_environment/assembler.py`):

| Constant | Value | Unit | npm env var (assembler only) |
| --- | --- | --- | --- |
| `NPM_REQUEST_TIMEOUT_MS` | 300000 | ms | `npm_config_fetch_timeout` |
| `NPM_RETRY_COUNT` | 3 | retries | `npm_config_fetch_retries` |
| `NPM_RETRY_MIN_TIMEOUT_MS` | 10000 | ms | `npm_config_fetch_retry_mintimeout` |
| `NPM_RETRY_MAX_TIMEOUT_MS` | 60000 | ms | `npm_config_fetch_retry_maxtimeout` |
| `ASSEMBLY_TOTAL_TIMEOUT_SECONDS` | 1800 | s | (constructor-owned; not an npm setting) |

Rationale: generous enough for normal corporate-network latency (5 minutes
per request, 3 retries, 10 s–60 s backoff), finite enough to guarantee a
bounded npm request/retry path.  The four npm fetch settings are rendered
into the assembler container environment only.  The 1800-second total
assembly duration is a reviewed constant that is included in canonical
policy identity and is not passed to npm; its runtime enforcement is
intentionally deferred to Phase 3.

### Phase 1 scope

Phase 1 does not enforce the total assembler deadline. It establishes and
identity-binds the reviewed value consumed by Phase 3.

### Deterministic identity change

- `npm_policy_digest()` now covers the canonical payload
  `{"flags": [...], "request_timeout_ms", "retry_count",
  "retry_min_timeout_ms", "retry_max_timeout_ms",
  "total_timeout_seconds"}` (key-sorted JSON, `separators=(",", ":")`).
- New digest: `f12116671feaab2f5c6bd00411fd098c475ff2142447ae3f9e935c9df74ac407`
  (previously derived over the flag list only).
- Changing any one limit changes the policy digest, the assembler identity,
  the assembler input identity, and the assembled output identity; a
  published output assembled under the prior policy no longer validates
  under a changed policy (`verify_output` returns `None`).

### Unchanged required npm flags

`npm_policy_flags()` still returns exactly
`("--ignore-scripts", "--no-bin-links", "--no-audit", "--no-fund")`; the
canonical assembler script is unchanged and still runs
`npm ci --ignore-scripts --no-bin-links --no-audit --no-fund`.

### No new CLI or inventory configuration surface

The limits are module-level constants, never read from `os.environ`/`os.getenv`,
and no assembler boundary (`compute_assembler_identity`, `preflight`,
`render_run_vector`, `assemble`) accepts a limit override parameter.  The
reviewed inventory (`docker-constructor.toml`) and the versioning
model/inventory modules declare no npm timeout/retry/duration field.

### Validation evidence

- New suite `tests/test_npm_environment_policy.py`: **14 tests OK**
  (`TestReviewedFiniteLimits` 5, `TestPolicyIdentity` 4,
  `TestPolicyRendering` 5).
- Updated existing suites for the four added assembler env vars:
  `test_npm_environment_run_vector.py`, `test_npm_environment_phase3_introspection.py`,
  `test_npm_environment_corporate_network.py` — all OK.
- Focused policy/identity/rendering/evidence-redaction/assembler-vector run:
  **98 tests OK (1 env-dependent skip)**.
- Full discovery (`python3 -m unittest discover -s tests`): **3227 tests OK,
  5 skips** (was 3213 before this phase).
- `python3 -m py_compile` over changed modules: OK.
- `ty check`: all checks passed.
- `docs/npm-environment-assembler.md` "Fixed npm policy" section documents
  the finite limits and their identity binding.
