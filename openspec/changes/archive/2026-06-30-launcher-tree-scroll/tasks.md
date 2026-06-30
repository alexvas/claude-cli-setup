## 1. Viewport state

- [x] 1.1 Add TUI viewport offset state for the visible slice of `flat_items`
- [x] 1.2 Clamp and recompute the viewport after cursor moves, expand/collapse, and resize events

## 2. Scrolling behavior

- [x] 2.1 Update Up/Down and `j`/`k` navigation so the highlighted item stays within the visible list area
- [x] 2.2 Render only the visible window of items based on the current viewport offset

## 3. Verification

- [x] 3.1 Manually verify downward scrolling in a tree taller than the terminal height
- [x] 3.2 Manually verify upward scrolling, expand/collapse behavior, and selection actions after scrolling
