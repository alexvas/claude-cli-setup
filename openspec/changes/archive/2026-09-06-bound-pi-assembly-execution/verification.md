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

## Phase 3 — Deadline, Interruption, and Mutable-State Cleanup

### Deadline supervision

- `DockerRunExecutor.run_streaming` accepts optional `deadline_seconds`,
  `container_name`, and `grace_seconds`.  A single daemon supervisor thread
  polls the client's own exit in short slices (a non-blocking
  ``proc.wait(timeout=0)`` reap plus a bounded ``cancel_event`` sleep) rather
  than blocking in one long ``proc.wait(timeout=deadline_seconds)``, so the
  deadline bounds only the assembler execution (client lifetime) and reader
  drain / sink finalization neither extend nor restart it.
- On expiry the supervisor terminates the local Docker client, independently
  force-removes the deterministic named container through a bounded
  `docker rm -f` client (wait → terminate → bounded wait → SIGKILL → final
  bounded wait), reaps the local client within `grace_seconds` (SIGKILL
  fallback), and closes both pipes so blocked readers always reach EOF.
  An already-absent daemon container remains idempotent success; an rm client
  that survives SIGKILL is retained as bounded cleanup context without an
  unbounded output read, while both of its output pipes are still closed.
  Readers then finish, the dispatcher finalizes, and a structured
  `AssemblyTimeoutError` (reason `"assembly_timeout"`) is raised with bounded
  redacted tails and any retained truncation notice; deadline-cleanup and
  pipe-close failures are bounded redacted notes, never the primary.
- `_terminate_and_remove` never blocks forever: the post-SIGKILL reap uses a
  bounded `proc.wait(timeout=grace_seconds)`; if that also expires the
  expiry is recorded as a cleanup error (`TimeoutError`) instead of waiting
  indefinitely, so the function always returns its collected errors in
  finite time.
- `_terminate_and_reap` (reader-failure path) is aligned with
  `_terminate_and_remove`: bounded terminate → wait → kill → bounded wait,
  collecting per-step errors (including a `TimeoutError` when the client
  still has not exited after SIGKILL) and returning them so the structured
  reader failure stays primary with the failed reap as bounded redacted
  secondary context.  Reader-failure cleanup closes the failed pipe
  immediately and, after the reap, closes both pipes through
  `_close_stream_pipes` (each close attempted independently) so the sibling
  reader always reaches EOF even when the client ignores terminate and
  survives kill; any pipe-close failure joins the reap/terminate failures as
  bounded redacted secondary context without replacing the reader failure.
- An unexpected failure from a poll never crashes the supervisor thread
  (which would strand the readers): it is recorded in shared supervisor
  state, the same bounded termination/reaping/container removal still runs
  to unblock the readers, and the supervisor is always joined before
  ``run_streaming`` returns or raises.  The recorded failure is surfaced as
  the primary error (bounded and redacted; control-flow exceptions propagate
  unchanged) with termination/reaping/container-removal and pipe-close
  failures attached as bounded redacted notes — ``AssemblyTimeoutError`` is
  reported only when the constructor-owned deadline actually expires (the
  monotonic clock, not a single poll timeout, decides expiry).
- Supervisor cleanup ownership is claimed atomically under the shared lock.
  An interruption that arrives before the supervisor claims cleanup sets the
  cancellation event and owns the terminate/remove/reap/pipe-close sequence;
  if the supervisor has already claimed deadline cleanup, interruption waits
  for that one cleanup rather than starting a concurrent second sequence.
  Thus a deadline that claimed cleanup first remains the primary
  ``AssemblyTimeoutError`` (the concurrent control-flow exception is a
  bounded redacted note), while an interruption that canceled first remains
  primary.  ``_join_supervisor`` and the already-owned-cleanup wait use the
  complete cleanup budget: three ``grace_seconds`` intervals for the bounded
  ``docker rm -f`` client (wait, terminate-wait, kill-wait), then one each
  for the local graceful reap, post-SIGKILL reap, and final pipe
  closure/scheduling — not one grace interval.  A supervisor still alive
  after that budget is recorded as a bounded ``TimeoutError`` and attached as
  a redacted shutdown note; supported paths never return or raise with an
  ``npm-deadline-supervisor`` thread alive.  Normal completion never cancels
  the supervisor: both pipes reaching EOF is not process completion, so the
  supervisor is joined *without* cancellation (``_wait_for_supervisor``,
  bounded by the assembly deadline plus cleanup grace) and keeps enforcing
  the deadline until it observes either a normal exit or the deadline expiry.
  The normal path then reuses the supervisor's bounded outcome (a reaped
  client on normal exit, or the deadline termination/reaping and a timeout)
  instead of an unbounded ``proc.wait()``. Deadline cleanup terminates,
  force-removes, and reaps the Docker client before closing pipes to release
  any remaining readers.
- `assemble()` routes the deadline and container name to the real streaming
  executor via signature introspection; injected Phase 2 executors without
  those parameters remain usable (no deadline).  `AssemblyTimeoutError` is
  re-raised unchanged through `assemble`'s existing cleanup boundary.

### Unified interruption cleanup

- `collect_streams` accepts `on_interruption`; a control-flow exception
  delivered to the coordinating thread (``KeyboardInterrupt``/``SystemExit``)
  invokes the hook.  When interruption owns cleanup it signals the supervisor
  cancellation event and terminates + force-removes + reaps + closes both
  pipes; when the supervisor already owns deadline cleanup, the hook waits
  for that bounded cleanup instead of issuing a concurrent second sequence.
  It then joins both readers, finalizes the dispatcher, and only then
  propagates the race winner with any cleanup failure as a bounded redacted
  note.  A hook that raises its own ``KeyboardInterrupt``/``SystemExit`` is
  caught as ``BaseException`` and recorded the same way, so the original
  interruption always remains primary unless the deadline had already won.
  ``run_streaming`` always supplies the hook, so interruption never strands
  the readers or the deadline supervisor.

### Cleanup and storage

- Streaming deadline/interruption cleanup exposes a thread-safe outcome to
  `assemble()`: once its bounded `docker rm -f` has been attempted for the
  named container, the outer failure boundary skips the duplicate normal
  `_cleanup_container` call while still always removing staging.  Remaining
  real-Docker `_cleanup_container` calls use bounded
  `subprocess.run(..., timeout=grace_seconds)` rather than
  `DockerRunExecutor.run()`'s unbounded subprocess path; already-absent
  containers (``No such container`` / ``No such object``) remain idempotent
  success and bounded cleanup failures remain notes on the original error.
- `assemble_environment` securely replaces abandoned same-input staging
  under the input-identity lock (no-follow removal; unsafe entries fail
  closed), never adopting it as a completed environment.
- Failed paths preserve the opaque npm cache and prior immutable published
  outputs; nothing partial is published; authoritative cache state is never
  chmod-ed, adopted, or deleted.

### Validation evidence

- New suite `tests/test_npm_environment_phase3_deadline.py`
  (deadline terminate/reap, bounded-grace SIGKILL escalation, accepted-chunk
  delivery, truncation-notice preservation under sink failure, named-container
  force-removal (including an rm client that survives terminate/SIGKILL),
  already-absent idempotency, ``KeyboardInterrupt`` reaping and
  propagation, assemble-level interrupt cleanup with an unreapable client that
  exercises the real 1800-second supervisor and its cancellation, stream-EOF
  before process-exit still enforcing the deadline (no premature
  cancellation of the supervisor), interruption racing a supervisor blocked
  in deadline cleanup (one cleanup owner, deadline-primary result, and no
  surviving workers), deadline pipe closure only after client termination and
  reaping (blocked readers released afterward), timeout skipping a later
  duplicate container removal that would block (timeout remains primary with
  no workers), no network
  classification on npm nonzero exits,
  bounded redacted diagnostics, cache/output preservation, and abandoned-
  staging replacement/unlinking) — all OK.
- Full npm-environment discovery (`test_npm_environment*.py`): all OK.
- Full discovery (`python3 -m unittest discover -s tests`): all OK.
- `python3 -m py_compile` over changed modules: OK.
- `ty check`: all checks passed.
- No ResourceWarning under `-W error::ResourceWarning`; no surviving reader,
  dispatcher, or deadline-supervisor threads after cleanup.

## Phase 4 — Reusable Process Lifecycle and Deadline Supervision

### Reuse and behavior preservation

`docker/npm_environment/lifecycle.py` now owns the domain-neutral lifecycle
policy/outcome values, bounded terminate/kill/reap primitives, bounded captured
subprocess runner, and `DeadlineSupervisor`. `DockerRunExecutor` supplies only
domain hooks for named-container removal and pipe closure; it retains Docker
naming, streaming redaction/dispatch, staging cleanup, and assembler exception
mapping outside the reusable supervisor.

The supervisor publishes cleanup ownership, timeout/poll-failure outcome, and
bounded join state under one lock. Its deadline is captured before the worker
thread is scheduled, and each cancellation wait is capped by the remaining
monotonic deadline, so a deadline shorter than the polling interval is not
delayed by a full polling slice.

### Validation evidence

- `tests/test_npm_environment_phase4_lifecycle.py` covers lifecycle reuse,
  captured dual-stream draining, bounded descendants holding pipes, descriptor
  safety, cleanup ownership, supervisor cleanup/poll failures, a poll-failure
  race where interruption retains primary status and the failure is secondary
  context, and a deadline shorter than the polling interval.
- Focused Phase 2–4 streaming, deadline, interruption, rootless, and lifecycle
  tests: all OK.
- Full discovery: `python -m unittest discover -s tests -p 'test_*.py'` —
  passed, with expected skips.
- `ty check docker --python-version 3.14 --output-format concise` — passed.
- `openspec validate bound-pi-assembly-execution --type change --strict --json`
  — passed.
