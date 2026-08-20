## Context

Build orchestration publishes an effective projection and returns its path as `publish_result.published_path`. The CLI facade currently adds that path to `CommandResult.data` whenever publication occurred. Generic text rendering then exposes the dictionary after the success message, even though the path is primarily internal metadata.

The output format and verbose flag are already available at the facade boundary, which is the authoritative location for deciding whether metadata belongs in a rendered result.

## Goals / Non-Goals

**Goals:**
- Keep ordinary successful text build output concise.
- Retain the published path in JSON and verbose text modes.
- Preserve publication and all non-presentation behavior.

**Non-Goals:**
- Stop creating the effective projection.
- Move or rename the projection file.
- Change JSON field names or build execution behavior.
- Introduce a general metadata filtering framework.

## Decisions

### Gate published-path result data at the facade boundary

The facade will add `published_path` to result data only when output is JSON or verbose mode is enabled. This keeps policy close to output selection while leaving orchestration presentation-neutral.

Changing the generic renderer was rejected because it would require renderer knowledge of build-specific metadata and could accidentally suppress similarly named fields from other commands.

### Preserve structured and diagnostic compatibility

JSON output will retain `data.published_path`, preserving automation compatibility. Verbose text will continue to expose the path for troubleshooting. Normal text will render only the concise success message when no other user-facing data is required.

## Risks / Trade-offs

- **[Users relying on parsing normal text lose the path]** → JSON is the supported machine-readable interface, and verbose mode remains available for diagnostics.
- **[Conditional data assembly could diverge between output modes]** → Add focused facade tests for normal text, verbose text, and JSON using the same build result.
