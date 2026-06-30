## Context

`docker/entrypoint.sh` currently performs unconditional recursive `chown -R dev:dev` on every configured `PROJECT_PATH_*` directory and on several directories in `/home/dev`. This is correct but expensive for large trees, especially caches such as `/home/dev/.npm`, because every startup reprocesses entries that already have the correct ownership. The startup script also needs to remain safe around symbolic links.

## Goals / Non-Goals

**Goals:**
- Reduce container startup time for ownership repair.
- Limit ownership changes to entries that are not already owned by `dev:dev`.
- Ensure recursive traversal does not follow symbolic links.
- Preserve the current startup contract: repair ownership first, then run the command as `dev`.

**Non-Goals:**
- Change mount layout, git safe-directory handling, or user switching behavior.
- Introduce new runtime dependencies beyond standard tools already present in the image.
- Replace ownership repair with permission-only changes.

## Decisions

- Replace unconditional `chown -R` with a selective scan using `find` and ownership predicates.
  - Rationale: scanning for mismatched ownership avoids invoking `chown` on already-correct trees, which is the main startup cost for large directories.
  - Alternative considered: keep `chown -R` and add opt-out knobs per directory. Rejected because it preserves the slow default path.
- Use traversal options that do not follow symbolic links.
  - Rationale: the requirement is to avoid crossing symlink boundaries while scanning recursive trees.
  - Alternative considered: post-filter symlinks after traversal. Rejected because avoiding traversal at the `find` level is simpler and safer.
- Keep the helper scoped to existing target directories only.
  - Rationale: this keeps the change minimal and preserves which paths are repaired today.
  - Alternative considered: redesign startup to track ownership state between runs. Rejected as unnecessary complexity.

## Risks / Trade-offs

- [Selective traversal still scans large trees] → Only mismatched entries are passed to `chown`, which reduces work even when traversal is unavoidable.
- [Shell/find portability issues] → Use standard GNU `find` features available in the Debian-based image and keep the logic simple.
- [Ownership predicates miss edge cases] → Apply the helper uniformly to both mounted projects and runtime cache directories and verify against mixed-ownership trees.

## Migration Plan

- Update `docker/entrypoint.sh` to use selective non-symlink traversal.
- Validate startup behavior against existing target paths and mixed ownership content.
- If regressions appear, revert the helper to the previous recursive ownership logic.

## Open Questions

- None.
