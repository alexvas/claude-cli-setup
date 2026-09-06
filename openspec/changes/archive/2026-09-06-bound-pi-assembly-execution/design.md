## Context

See `proposal.md` for motivation. Pi is now assembled before BuildKit by a standalone named Docker container running the fixed script-free npm policy. Production execution currently waits through a fully captured `subprocess.run`; therefore npm warnings are unavailable until exit, output can grow in memory, and neither npm registry waits nor total container runtime has a constructor-owned deadline. Existing constraints require secret redaction, clean JSON stdout, immutable assembler identity, input-identity locking, opaque shared npm-cache reuse, and cleanup of mutable staging without damaging published environments.

## Goals / Non-Goals

**Goals:**

- Make each pre-BuildKit Pi materialization phase observable in text mode.
- Bound npm request/retry behavior and total assembler runtime.
- Stream redacted diagnostics while retaining bounded tails for failures.
- Guarantee container and staging cleanup across timeout and interruption.
- Factor process lifecycle management into small reusable primitives and one reusable deadline supervisor without moving Docker-, streaming-, or storage-specific policy into the generic layer.
- Preserve JSON-output isolation, opaque cache reuse, and existing immutable publication rules.

**Non-Goals:**

- Guarantee a maximum duration for the main BuildKit build.
- Parse npm's human-readable output into package-level semantic progress.
- Treat npm cache contents as verified or authoritative.
- Automatically delete the shared npm cache after a slow or failed request.
- Add user-facing timeout configuration in this change.

## Decisions

### Use reviewed built-in network and total-runtime limits

Add fixed npm configuration to the assembler environment for fetch timeout, retry count, and retry backoff, plus a constructor-owned total execution deadline. Use conservative values that permit normal corporate-network latency while ensuring finite failure; record the selected constants and rationale in tests and verification evidence. Include npm network settings in the canonical policy bytes/digest, and bind the total runtime policy alongside the executor policy so a behavioral policy change invalidates assembler identity.

npm fetch timeout or retry exhaustion cannot be reliably distinguished from other npm failures by exit code. Constructor therefore treats npm's nonzero exit as a structured assembler failure with bounded, redacted diagnostics and does not parse npm's human-readable output to infer a network-specific classification. The npm limits make npm's own request/retry path finite; the independent outer deadline guarantees termination if npm does not exit despite those limits. Timeout-specific classification is reserved for expiry of that constructor-owned outer deadline.

A user-configurable timeout was rejected because it would add unreviewed behavioral variance and another configuration surface. Relying only on npm defaults was rejected because defaults can change with the pinned npm version and do not bound the outer Docker process. Parsing npm diagnostics was rejected because their human-readable format is not a stable classification interface.

When the existing resolved corporate trust policy supplies a reviewed host CA bundle, mount it at the fixed container path `/etc/ssl/certs/ca-certificates.crt` and also set `npm_config_cafile=/etc/ssl/certs/ca-certificates.crt` for the standalone assembler. Node and npm do not necessarily use the operating-system CA store automatically, so the explicit npm setting is required for the mounted trust bundle to affect registry requests. The environment contains only the fixed container path: the machine-local host trust path remains a redacted runtime secret and is absent from evidence and assembled output. This is an integration correction to the existing corporate trust policy, not a new configuration surface or assembler-identity input.

### Replace all-at-once capture with a redacting streaming executor

Run the named container with stdout and stderr pipes drained concurrently to avoid pipe deadlock. Read each pipe in chunks of at most 16 KiB and incrementally decode UTF-8 so multibyte characters split across byte reads remain intact. Normalize the configured secrets into a deduplicated multi-pattern matcher. At each leftmost match position, select the longest complete matching value, independent of caller-provided secret order; overlapping values and values that are substrings of others therefore produce deterministic output. Replace the complete selected value with exactly one redaction marker, consume the complete match, and continue from its end so no remainder from a shorter alternative is exposed.

For each stream, retain an overlap of at least `L - 1` decoded characters where `L` is the longest configured secret, and emit the preceding safe prefix immediately without waiting for a newline. No candidate secret prefix or suffix is emitted until enough input exists to determine whether it forms a complete longest match. At EOF, flush the incremental decoder, process its final decoded characters through the same deterministic matcher, and emit the final safe partial record.

Retain at most 64 KiB of UTF-8 diagnostic tail independently for stdout and stderr. Outside the current bounded read chunk and retained tail, each stream's pending decoded overlap is at most `max(0, L - 1)` characters and the UTF-8 incremental decoder retains at most three incomplete bytes. These bounds hold independently of total output size, including arbitrarily long output without newlines.

Text-mode build orchestration supplies one shared optional diagnostic sink for both stdout and stderr. The supported sink is a constructor-owned, non-blocking callback: it may enqueue or write one already-redacted, stream-tagged chunk, but it must return promptly and must not perform an indefinitely blocking operation. Python threads executing arbitrary callbacks cannot be cancelled safely, so a callback that violates this contract is unsupported; Constructor does not claim that it can cleanly stop an arbitrary callback that never returns. JSON and noninteractive callers create no sink and receive only bounded diagnostics on failure.

Pipe readers never invoke the sink directly. They submit already-redacted chunks with non-blocking writes to one bounded queue of at most 64 chunks; one dispatcher serializes every sink invocation. A slow-but-returning sink may lag only within that queue bound. If the queue is full, readers continue draining pipes and may drop only chunks that cannot be accepted without blocking; independent retained tails remain intact, and one redacted truncation notice records the live-delivery loss. If the sink raises or otherwise fails its supported prompt-return contract, live delivery is disabled and undeliverable accepted chunks may be discarded, while pipe draining and retained-tail collection continue and one redacted truncation notice records that accepted live output was not delivered.

Normal finalization begins only after both stdout and stderr readers reach EOF, flush their incremental decoders, process final redaction overlap, and enqueue their final redacted partial chunks. The queue then stops accepting new chunks. When no overflow or sink failure occurred, the dispatcher drains every accepted chunk in queue-acceptance order to the compliant sink, including final partial output, exits, and is joined before assembly returns or propagates its result. No accepted chunk is discarded during ordinary completion, and no diagnostic callback may begin or continue after assembly returns.

Each constructor-owned sink invocation has a supported maximum duration of 100 ms, and total dispatcher draining after reader completion has a 10-second finalization budget. A callback that returns after 100 ms is treated as a sink-contract failure: subsequent live delivery is disabled, pending accepted chunks may be discarded, and one redacted truncation notice is retained. If the 10-second drain budget expires between compliant callback invocations, remaining queued chunks are discarded with the same retained notice and the dispatcher exits and is joined. A callback that never returns remains an unsupported contract violation because Python cannot safely cancel it; it is not a supported lifecycle guarantee.

Timeout or interruption first terminates the Docker client so pipe readers can reach EOF; if a reader cannot finish within the existing bounded process-cleanup grace period, its stream is closed and any safely decodable final state is processed before dispatcher shutdown. Already accepted chunks are delivered within the remaining 10-second finalization budget where possible. Queue overflow may lose only chunks that were never accepted; forced reader termination may leave unread process output; sink failure or finalization-budget exhaustion may abandon accepted chunks. Any such live-delivery loss produces one retained redacted truncation notice without replacing the primary timeout or interruption result. Sink finalization does not extend or restart the assembler execution deadline; it is a separate bounded cleanup step.

Host-materialization progress is finalized only after reader EOF handling, dispatcher drain, and dispatcher join, and before native BuildKit progress starts, so final assembler diagnostics are delivered first and delayed diagnostics cannot interleave with BuildKit output.

The derived-environment attestation carries two distinct assembler-evidence digests. The existing canonical evidence-body digest remains the value bound into assembled-output identity and passed to in-image semantic verification. A separate SHA-256 digest of the exact serialized evidence bytes binds host snapshot admission and transport. Snapshot validation SHALL compare the serialized bytes only with the serialized-evidence digest and SHALL independently parse the evidence and verify its canonical body digest; the two values are never substituted for one another. Both are included in derived-environment identity/rendering so changing either invalidates the materialized build input.

Direct inheritance of the terminal was rejected because it cannot enforce redaction or retain bounded failure context. Keeping `capture_output=True` was rejected because it hides liveness and allows memory growth proportional to process output. Newline-delimited buffering was rejected because one arbitrarily long unterminated record would delay progress and violate the memory bound. Direct calls from both pipe readers were rejected because concurrent writes can corrupt a non-thread-safe sink, while blocking readers on sink backpressure can deadlock the subprocess.

### Route host progress and diagnostics through one typed event sink

Define one immutable host-build event union at the facade-to-orchestration boundary. A `HostPhaseEvent` carries a fixed phase and state; a `HostDiagnosticEvent` carries a fixed phase, the stdout/stderr stream tag, and an already-redacted text chunk. The fixed host phases are Pi release acquisition, locked dependency assembly, derived-environment validation, and transition to the Docker build. Phase states are `started`, `succeeded`, and `failed`. Events carry presentation-neutral facts rather than terminal control sequences, mutable progress handles, exception objects, or Docker progress settings.

The sink is an optional prompt-returning callable supplied downward by the facade through build orchestration and Pi materialization. Only interactive text mode constructs the constructor-owned presentation sink. JSON mode, noninteractive or redirected text execution, dry-run planning, SDK callers, and existing injected materializers or executors that omit the optional sink create no live-output channel and retain their existing behavior. Domain modules never print directly and never inspect CLI output mode; the facade alone selects and renders presentation. Optional parameters are capability-detected or default to `None` so existing injected protocols remain valid.

Orchestration emits `started` synchronously before entering each potentially blocking phase and exactly one matching terminal event afterward: `succeeded` after normal completion or `failed` before propagating an exception. A failed phase never emits `succeeded`, later host phases do not start, and Docker is not invoked. Fast and warm-cache paths still emit a coherent start/terminal pair. Phase labels are fixed constructor text and do not include unredacted exception details.

During locked dependency assembly, the executor adapts its existing serialized diagnostic dispatcher to emit `HostDiagnosticEvent` values tagged with that phase and source stream. Diagnostic text is already redacted before it crosses the event boundary. The adapter does not replay streamed chunks when the final operational error is rendered; bounded retained tails remain available for callers and failure context under the existing redaction rules. Reader EOF processing, final partial-chunk acceptance, queue drain, and dispatcher join all complete before the assembly call returns or raises, so the orchestration layer cannot emit the assembly phase's terminal event while a diagnostic callback remains active.

After release acquisition, assembly, and derived validation have each reached a terminal state, orchestration emits the Docker-transition start event. The facade finalizes and clears host progress, then the transition receives its success state immediately before the existing Docker invocation. Native BuildKit output may begin only after those synchronous callbacks return. The event protocol does not alter or wrap the selected Docker `--progress` argument, and delayed assembler output cannot interleave with BuildKit output.

The constructor-owned presenter is required to return promptly and not raise. At the reusable boundary, a sink exception disables subsequent live presentation and is retained only as secondary presentation context; it must not replace a timeout, interruption, assembler failure, or Docker result, and must not cause another build phase to run or be skipped. The existing assembler queue, 100 ms invocation contract, and 10-second finalization budget remain authoritative for asynchronous diagnostic delivery. Arbitrarily blocking third-party callbacks remain unsupported because Python cannot cancel them safely.

Separate lifecycle and diagnostic callbacks were rejected because they permit unsynchronized terminal writers and leave transition ordering implicit. Passing terminal/progress renderer objects into domain modules was rejected because it couples materialization to CLI presentation and Docker output modes. Replaying retained diagnostic tails after live delivery was rejected because it duplicates output and can reorder diagnostics around the phase failure.

### Factor process lifecycle into small reusable primitives

Represent process lifecycle policy and outcome explicitly, then centralize the mechanics shared by the primary `docker run` client and short-lived cleanup clients. A bounded termination/reaping primitive accepts an already-started process and owns the terminate, bounded wait, SIGKILL fallback, final bounded reap, and descriptor-closure sequence. A bounded captured-process runner starts a simple auxiliary command and builds on that primitive rather than reproducing a second wait/terminate/kill implementation. Both return structured lifecycle outcomes so callers can preserve the primary failure and attach cleanup failures without parsing exception text.

Use one reusable deadline supervisor for monotonic deadline polling, cancellation, atomic cleanup ownership, bounded supervisor joining, and publication of a structured lifecycle outcome. The supervisor accepts explicit cleanup hooks and coordinates when they run, but it does not know about Docker container names, npm diagnostics, redaction, stream decoding, sink dispatch, staging paths, or assembler exception classes. The assembler execution layer remains the domain orchestrator: it supplies independent named-container removal and pipe-unblocking hooks, finalizes streaming diagnostics, removes staging at the outer boundary, and maps lifecycle outcomes to `AssemblyTimeoutError` or the original control-flow/operational exception.

Keep cleanup-error presentation separate from lifecycle execution. Helpers that redact and attach bounded cleanup notes consume lifecycle outcomes but are not part of process supervision. This separation lets the same lifecycle primitives serve both streamed and captured subprocesses while keeping security-sensitive redaction and primary-exception precedence explicit at the assembler boundary.

A single universal subprocess function parameterized by many Docker-, streaming-, and exception-specific callbacks was rejected because it would obscure cleanup ownership and ordering. Separate ad hoc supervisors for `docker run` and every auxiliary command were also rejected because they duplicate deadline, cancellation, kill, reap, and descriptor rules. Small typed primitives plus one domain-neutral supervisor provide reuse without weakening the explicit assembler cleanup boundary.

### Separate durable progress events from raw assembler diagnostics

Build orchestration emits coarse lifecycle events before release acquisition, assembly, validation, and the main Docker build. These events provide liveness even when npm emits nothing. Raw npm output remains diagnostic and is streamed only in text mode. The facade owns formatting and output-mode routing so domain modules do not print directly.

Treating npm log lines as the sole progress source was rejected because npm can legitimately remain quiet for long periods and its format is not a stable API.

### Enforce timeout with terminate, force-remove, and reap

When the deadline expires, terminate the local Docker client, invoke independent force-removal of the deterministic container name, wait for both processes with a bounded grace period, and return a structured timeout error. The existing assembly `finally` boundary remains responsible for staging cleanup. The same force-removal path applies to cancellation and interruption, while control-flow exceptions continue to propagate after cleanup.

Killing only the local `docker run` client was rejected because the daemon-side container can survive. Waiting indefinitely for graceful npm shutdown was rejected because it defeats the deadline.

### Preserve opaque cache and published outputs

Failure cleanup removes only the current mutable staging and container. It does not clear the assembler-wide npm cache or prior content-addressed outputs. Same-input staging handling remains under the existing input-identity lock: stale mutable state is no-follow validated and securely replaced or rejected before a new run, never adopted as output.

Automatic cache deletion was rejected because the observed stall does not establish cache corruption and downloaded tarballs can accelerate a safe retry.

## Risks / Trade-offs

- [Streaming redaction can miss a secret split across read or emission boundaries or expose a suffix when secrets overlap] → Use caller-order-independent leftmost-longest multi-pattern matching, retain at least the longest-secret-minus-one overlap, replace each complete selected value with one marker, and test overlapping, substring, boundary, and EOF cases.
- [A slow or failing sink can exhaust memory, lose diagnostics, or delay finalization] → Serialize delivery through a 64-chunk non-blocking queue, drain all accepted chunks on normal completion, restrict dropping to overflow or sink-contract failure, enforce the 100 ms invocation contract and 10-second drain budget, retain one truncation notice for delivery loss, and join the dispatcher before return.
- [An arbitrary sink callback can block forever and Python cannot safely cancel its executing thread] → Support only constructor-owned callbacks that return promptly; treat violation as unsupported rather than promising lifecycle cleanup for an uncancellable callback.
- [npm may exceed conservative limits on unusually slow networks] → Choose documented generous built-in values and return a diagnostic that identifies the elapsed phase and policy limit.
- [Force-removal races with natural container exit] → Treat already-absent containers as successful cleanup and preserve the original result.
- [Concurrent pipe draining and timeout handling can leak threads or descriptors] → Centralize process lifecycle ownership and test success, nonzero exit, timeout, cancellation, and sink failure.
- [An over-general callback-driven supervisor can hide cleanup ownership or reorder domain cleanup] → Keep typed lifecycle primitives small, expose structured outcomes, and retain named-container, pipe, sink, redaction, staging, and exception mapping in the explicit assembler orchestration layer.
- [Policy identity changes cause a cold assembly] → Preserve the shared opaque npm download cache so package bytes remain reusable.

## Migration Plan

1. Introduce bounded process execution and cleanup behind the existing executor protocol while retaining compatibility for injected test executors.
2. Add fixed npm network limits and update assembler policy identity fixtures.
3. Route optional redacted progress through build orchestration and the CLI output-mode boundary.
4. Validate cold, warm-cache, timeout, interruption, text, and JSON builds.
5. Roll back by reverting the change; old published environments remain independently content-addressed, while the opaque cache remains reusable.
