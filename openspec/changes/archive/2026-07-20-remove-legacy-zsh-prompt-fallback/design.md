## Context

The previous interface-alignment change introduced `/home/dev/.pi-zsh-prompt` and temporarily retained `.claude-cli-zsh-prompt` as a fallback. Current builds and documentation are Pi-oriented, while `locate` still finds the old filename inside rootless containerd overlayfs snapshots created by earlier images.

The fallback is not needed for the current runtime contract. Docker snapshots may remain until their owning image, build cache, or container is pruned, so source cleanup and Docker storage cleanup are separate concerns.

## Goals / Non-Goals

**Goals:**
- Make the Pi prompt path the sole supported project-owned path.
- Remove obsolete Claude identity from shell setup, specs, and user documentation.
- Provide safe host-side cleanup guidance for stale Docker snapshots.

**Non-Goals:**
- Manually delete files from containerd overlayfs snapshot directories.
- Remove unrelated Docker images, volumes, or user data automatically.
- Change prompt content or zsh startup behavior beyond the path selection.

## Decisions

### Make the Pi path exclusive

The generated `.zshrc` SHALL source `/home/dev/.pi-zsh-prompt` when present and SHALL not attempt the legacy path. This makes missing migration explicit instead of silently loading stale content.

### Use Docker cleanup commands for stale snapshots

Documentation will recommend inspecting storage with `docker system df -v`, then using targeted `docker builder prune` and image/container cleanup as appropriate. It will warn against direct deletion under rootless containerd storage and against pruning volumes without reviewing their contents.

### Do not provide prompt migration

Only the Pi prompt path is supported. Existing prompt files under obsolete names are intentionally ignored; the change does not add migration logic or documentation.

## Risks / Trade-offs

- [Users with only the legacy file lose their prompt customization] → Document the one-time copy/rename to `.pi-zsh-prompt` before upgrading.
- [Old snapshots remain after source cleanup] → Explain that Docker storage cleanup is separate and provide safe prune commands.
- [Aggressive pruning removes useful build cache] → Recommend targeted inspection and explicitly avoid `--volumes` by default.
