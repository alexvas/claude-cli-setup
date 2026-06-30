## Why

The launcher TUI currently lets the highlighted selection move past the visible bottom edge when the directory tree is taller than the terminal. This makes it unclear which directory is selected and makes large trees difficult to navigate.

## What Changes

- Add vertical scrolling to the launcher tree view when the current selection reaches the visible top or bottom edge.
- Keep the highlighted row within the visible list area while moving through long trees with Up/Down or `j`/`k`.
- Preserve existing expand/collapse and selection behavior while the list is scrolled.
- Update launcher requirements to define viewport scrolling behavior for oversized trees.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `project-launcher`: change TUI navigation requirements so long directory trees scroll within the viewport instead of letting the highlighted selection move off-screen.

## Impact

- Affected code: `launch-pi.py`
- Affected behavior: curses TUI navigation and rendering for large directory trees
- Affected systems: launcher keyboard handling, visible item rendering, cursor/viewport state management
