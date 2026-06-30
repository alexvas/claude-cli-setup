## Context

`launch-pi.py` renders the project selector as a flat list in curses and stores the selected item as a single `cursor` index into `flat_items`. Rendering currently starts at a fixed top row and draws items until visible rows are exhausted. When the tree becomes taller than the viewport, Up/Down changes `cursor` but does not change the rendered start offset, so the highlighted selection can move outside the visible region.

## Goals / Non-Goals

**Goals:**
- Keep the current selection visible while moving through long trees.
- Add vertical viewport scrolling for both downward and upward navigation.
- Preserve the existing selection model, expand/collapse behavior, and launch actions.
- Keep the implementation local to the launcher TUI logic.

**Non-Goals:**
- Redesign the overall TUI layout or keybindings.
- Add paging, mouse support, or horizontal scrolling.
- Change how project trees are discovered or flattened.

## Decisions

- Add a persistent viewport offset for the visible slice of `flat_items`.
  - Rationale: the bug is caused by rendering always starting from the first item. A separate scroll offset fixes visibility without changing selection semantics.
  - Alternative considered: clamp `cursor` to visible rows only. Rejected because it would prevent navigating the whole tree.
- Normalize the viewport after every navigation or tree rebuild.
  - Rationale: expand/collapse can change list length and move items around, so the viewport must be recomputed to keep the cursor visible.
  - Alternative considered: update offset only on Up/Down keys. Rejected because collapse or resize could still leave the cursor off-screen.
- Render only the visible window of `flat_items` using the current offset.
  - Rationale: it directly matches curses screen constraints and keeps status/header rows unchanged.
  - Alternative considered: draw all rows and rely on curses clipping. Rejected because selection visibility would remain implicit and harder to control.

## Risks / Trade-offs

- [Viewport math gets out of sync after expand/collapse] → Recompute and clamp the offset whenever `flat_items` changes.
- [Very small terminals expose edge cases] → Reuse the existing minimum-height handling and clamp visible ranges to non-negative values.
- [Behavior changes for users accustomed to wraparound-only navigation] → Keep existing item ordering and movement keys; only the viewport behavior changes.

## Migration Plan

- No data migration is required.
- Update `launch-pi.py` and verify navigation manually in a tall tree.
- If regressions appear, revert the viewport state changes in the launcher TUI code.

## Open Questions

- None.
