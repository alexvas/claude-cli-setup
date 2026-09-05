# Verification — bound-pi-assembly-execution

Run Date: 2026-09-04T15:23:09Z (Phase 1), 2026-09-04T16:18:27Z (Phase 2)

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

- New suite `tests/test_npm_environment_policy.py`
  (`TestReviewedFiniteLimits`, `TestPolicyIdentity`, `TestPolicyRendering`) —
  all OK.
- Updated existing suites for the four added assembler env vars:
  `test_npm_environment_run_vector.py`, `test_npm_environment_phase3_introspection.py`,
  `test_npm_environment_corporate_network.py` — all OK.
- Focused policy/identity/rendering/evidence-redaction/assembler-vector run:
  all OK.
- Full discovery (`python3 -m unittest discover -s tests`): all OK.
- `python3 -m py_compile` over changed modules: OK.
- `ty check`: all checks passed.
- `docs/npm-environment-assembler.md` "Fixed npm policy" section documents
  the finite limits and their identity binding.

## Phase 2 — Bounded Redacted Streaming Executor

### Streaming redaction and decoding

`docker/npm_environment/streaming.py` adds the Phase 2 primitives:

- `redact_text`/`RedactingStream`: deterministic caller-order-independent
  leftmost-longest multi-pattern redaction.  At the leftmost position where
  any configured secret matches, the longest complete match is replaced by
  exactly one `<redacted>` marker and consumed whole, so no suffix of a
  shorter alternative is exposed.  Streaming retains
  ``longest_secret - 1`` decoded characters of overlap and only commits a
  match once a full ``longest_secret`` window follows its start (or at EOF),
  so no candidate prefix or suffix is emitted before the full match is
  determined.
- Incremental UTF-8 decoding via ``codecs.getincrementaldecoder("utf-8")``
  (split multibyte characters stay intact; decoder holds at most three
  incomplete bytes) with EOF flushing of the final partial record.
- Independent 64 KiB (UTF-8 byte) retained diagnostic tails per stream via
  ``RedactingStream`` (bounded independently of total output).
- ``SinkDispatcher``: one serialized dispatcher thread behind a non-blocking
  64-chunk queue; dropping restricted to queue overflow or sink-contract
  failure; exactly one retained redacted truncation notice
  (``<live output truncated>``); 100 ms per-callback budget; 10-second
  dispatcher-drain budget; dispatcher joined before executor return.
  Arbitrarily indefinitely blocking callbacks are documented as unsupported
  (Python cannot safely cancel a running callback thread).
- ``collect_streams`` drains two byte pipes concurrently with 16 KiB reads.

### Executor integration

- `DockerRunExecutor.run_streaming` replaces all-at-once capture for the
  real executor: ``subprocess.Popen`` with both pipes drained concurrently,
  redacted safe prefixes reaching the optional sink before exit, bounded
  redacted tails returned, and pipe descriptors closed after draining.
- `assemble(..., sink=...)` accepts an optional constructor-owned sink;
  an absent sink produces no live output and retains only bounded
  diagnostics.  Executors without ``run_streaming`` (existing injected
  ``RunExecutor`` implementations) remain usable via the bounded
  all-at-once fallback (`redact_tail`).
- `ProcessResult`/`AssemblyRun` gain an optional ``truncation_notice``; a
  nonzero exit reports redacted bounded diagnostics plus any retained
  truncation notice.

### Validation evidence

- New suite `tests/test_npm_environment_streaming.py`
  (redaction determinism/overlap, incremental decoding, 64 KiB tail and
  overlap bounds, concurrent-stream sink delivery, serialized single-thread
  sink, bounded reads, slow-compliant/raising/overflow sinks, normal
  finalization join, 100 ms and 10-second budgets, injected-executor
  compatibility) — all OK.
- Updated `tests/test_npm_environment_rootless.py` for the executor's
  ``subprocess.Popen`` streaming path (empty-pipe stub) — OK.
- Full npm-environment discovery (`test_npm_environment*.py`): all OK.
- Full discovery (`python3 -m unittest discover -s tests`): all OK.
- `python3 -m py_compile` over changed modules: OK.
- `ty check`: all checks passed.
- No ResourceWarning under `-W error::ResourceWarning` (pipe descriptors
  closed after draining).
