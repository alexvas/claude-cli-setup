## Context

`docker/entrypoint.sh` now uses a selective recursive ownership repair helper for configured project mounts and several `/home/dev` cache directories. The next requirement is analogous permission repair: ensure group write access is present on the same top-level directories, but avoid unconditional recursive `chmod` across large trees such as `/home/dev/.npm`. The traversal must remain bounded to the same trees and must not follow symbolic links.

## Goals / Non-Goals

**Goals:**
- Add selective `chmod g+w` repair for the same startup target directories as ownership repair.
- Change permissions only for files and directories that are missing group write access.
- Avoid following symbolic links during recursive traversal.
- Keep the startup flow and path coverage aligned with the existing ownership helper.

**Non-Goals:**
- Change which top-level directories are repaired on startup.
- Introduce ACLs, broader mode normalization, or per-path configuration.
- Replace or redesign the existing ownership repair behavior.

## Decisions

- Add a second selective helper for group-write repair rather than folding permission logic into unconditional mode changes.
  - Rationale: separate focused helpers keep intent clear and allow permissions to be changed only where needed.
  - Alternative considered: run `chmod -R g+w` after ownership repair. Rejected because it repeats the same performance issue on large trees.
- Use `find` predicates to target only entries lacking group write permission.
  - Rationale: the startup cost should scale mostly with the number of non-compliant entries rather than rewriting every inode.
  - Alternative considered: rely on ownership repair alone. Rejected because correct ownership does not guarantee the required group-write mode.
- Keep traversal non-symlink-following, matching ownership repair semantics.
  - Rationale: this avoids modifying files outside the intended directory trees through symlink edges.
  - Alternative considered: skip only symlink leaves while following directory symlinks. Rejected as riskier and inconsistent with the existing repair contract.

## Risks / Trade-offs

- [Permission scan still traverses large trees] → Only non-compliant entries receive `chmod`, avoiding expensive bulk updates on already-correct trees.
- [Mode predicates may behave differently for files and directories] → Apply the same `g+w` requirement uniformly to both types because the request is scoped to top-level trees, not type-specific modes.
- [Combining ownership and permission repairs could complicate the script] → Keep the helpers small and apply them sequentially to the same path list.

## Migration Plan

- Update `docker/entrypoint.sh` with a selective group-write repair helper.
- Apply it to each existing startup repair target alongside ownership repair.
- Validate shell syntax and verify the OpenSpec change after artifact creation.
- If regressions appear, revert the permission helper while keeping the ownership optimization intact.

## Open Questions

- None.
