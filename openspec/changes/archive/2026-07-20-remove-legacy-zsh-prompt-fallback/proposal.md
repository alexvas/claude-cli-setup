## Why

The Pi image now writes and loads `/home/dev/.pi-zsh-prompt`, but still carries a compatibility branch for the retired `.claude-cli-zsh-prompt` filename. That fallback preserves obsolete identity and can hide stale prompt files left in old Docker image snapshots; the migration window is no longer needed.

## What Changes

- Remove the legacy `.claude-cli-zsh-prompt` fallback from generated zsh configuration.
- Keep `/home/dev/.pi-zsh-prompt` as the only project-owned prompt path.
- Remove migration/fallback wording from the Docker runtime specification and maintained README files.
- Document verification and optional Docker cache/image cleanup for stale containerd snapshots; do not delete containerd snapshot directories manually.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `docker-runtime`: zsh loads only the Pi prompt fragment and no longer supports the retired Claude-named prompt file.

## Impact

- Affects `docker/setup-zsh.sh`, `openspec/specs/docker-runtime/spec.md`, and the Russian, English, and Chinese README files.
- Existing prompt customizations outside `.pi-zsh-prompt` are no longer supported.
- Old files in unused Docker image/build-cache snapshots are operational leftovers and are cleaned through Docker commands, not application code.
