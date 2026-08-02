## Context

Interactive `run` inherits the host terminal through an attached `docker run` process. `Ctrl-C` typed in that terminal is expected to affect the foreground application inside the container and does not represent facade termination. The defect occurs when the host sends `SIGTERM` to the Python facade process itself: the facade exits while the container can continue running, and `--rm` does not remove it because the container has not exited.

The launcher already owns a unique allocated `pi-N` name and an ephemeral runtime projection, so it can perform exact cleanup without scanning or affecting unrelated containers. Unit tests must remain Docker-daemon-independent.

## Goals / Non-Goals

**Goals:**

- On host-sent facade `SIGTERM`, terminate the container owned by the active launch and reap the attached Docker client before releasing the runtime projection.
- Preserve conventional SIGTERM status 143.
- Make signal handling and cleanup injectable, narrowly targeted, observable in tests, and best-effort without masking the primary termination outcome.
- Preserve normal interactive terminal behavior, including container-local `Ctrl-C`.

**Non-Goals:**

- Converting container-local `Ctrl-C` into facade termination.
- Removing unrelated or previously existing `pi-N` containers.
- Recovering from uncatchable `SIGKILL` or host failure.
- Changing run vectors, `--rm`, naming allocation, mounts, project selection, or evidence behavior.
- Building a general Docker process supervisor.

## Decisions

### Treat facade SIGTERM as a scoped termination request

Install a temporary `SIGTERM` handler only around the active `run` transaction on the main thread. The handler converts SIGTERM into a dedicated internal termination exception/control flow that unwinds through launcher-owned cleanup. Restore the previous handler in `finally`.

This is preferred over relying on process-finalization hooks, which are not guaranteed to run after default SIGTERM termination. `SIGKILL` remains explicitly unsupported because it cannot be caught.

### Add a narrow owned-container cleanup boundary

Introduce an injected cleanup operation that receives the exact container name allocated by the current transaction and performs the equivalent of `docker rm --force <name>`. It must not discover containers by prefix. An absent/already-removed target is idempotent success.

Killing only the local `docker run` client is insufficient because client disconnection does not guarantee container termination.

### Reap the attached Docker client

The interactive process boundary must not leave its `docker run` child orphaned when termination control flow interrupts the wait. It shall terminate/reap the client as needed after owned-container removal. The implementation may use a managed `Popen` boundary or equivalent injectable process abstraction; it must preserve normal inherited terminal streams.

### Clean the container before the projection

Handle termination inside the runtime projection context. On the dedicated SIGTERM path, attempt exact owned-container removal while the projection still exists, ensure the attached Docker client is reaped, then allow the projection context manager to unlink the file.

### Preserve the primary termination outcome

Cleanup failure is secondary. Record or render it as supplemental diagnostic information where possible, but preserve SIGTERM semantics and exit status 143. Cleanup failure MUST NOT turn termination into success or an ordinary operational run result.

### Verify without Docker in unit tests

Use injected signal hooks, fake interactive process handles, and fake cleanup executors to assert exact ordering, target identity, child reaping, status preservation, cleanup-failure behavior, and projection lifecycle. Docker-host acceptance sends SIGTERM directly to the facade PID and confirms no container, Docker client, or projection remains.

## Risks / Trade-offs

- **Cleanup command hangs or fails** → Bound cleanup, preserve status 143, and expose a supplemental warning.
- **Container exits before forced removal** → Treat not-found/already-removed as idempotent success.
- **Signal handler leaks into other commands** → Scope it to active `run` and always restore the previous handler.
- **Signal arrives before container creation** → Exact removal may report not-found; still reap the client and clean the projection.
- **Double cleanup from concurrent exit paths** → Make cleanup idempotent and target only the transaction's allocated name.
- **Force removal destroys in-container work** → It applies only when the host explicitly terminates the owning facade and only to that ephemeral `--rm` container.
