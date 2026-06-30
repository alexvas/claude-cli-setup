#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///

"""Launch π Docker container with IDE integration.

Provides a TUI for selecting main and additional projects,
then runs docker compose with the appropriate mounts, env vars,
and port forwarding.

Usage:
  uv run launch-pi.py                   # auto-detect main project, no TUI
  uv run launch-pi.py --tui             # interactive project selection
  uv run launch-pi.py --dry-run         # print command, don't run
  uv run launch-pi.py --light           # light theme (with --tui)
  uv run launch-pi.py --no-forward      # skip socat port forwarding
"""

from __future__ import annotations

import argparse
import atexit
import curses
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
COMPOSE_FILE_BASE = REPO_ROOT / "docker-compose.yml"


@dataclass
class TreeNode:
    path: Path
    name: str
    expanded: bool = False
    has_subdirs: bool = False
    children: list["TreeNode"] = field(default_factory=list)
    depth: int = 0


@dataclass
class FlatItem:
    kind: str  # "ide" | "tree" | "separator"
    label: str
    indent: int = 0
    ide_index: int | None = None
    node: TreeNode | None = None


def build_tree(root: Path, depth: int = 0, max_depth: int = 5) -> list[TreeNode]:
    """Return only subdirectories of *root*, sorted alphabetically."""
    if depth >= max_depth:
        return []
    entries: list[TreeNode] = []
    try:
        for p in sorted(root.iterdir(), key=lambda p: p.name):
            if not p.is_dir():
                continue
            has_subdirs = (
                any(q.is_dir() for q in p.iterdir()) if depth + 1 < max_depth else False
            )
            entries.append(
                TreeNode(
                    path=p,
                    name=p.name,
                    expanded=False,
                    has_subdirs=has_subdirs,
                    depth=depth,
                )
            )
    except PermissionError:
        pass
    return entries


def load_env() -> dict[str, str]:
    """Parse REPO_ROOT/.env as simple KEY=VALUE pairs."""
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            result[key] = value
    return result


def next_container_num() -> int:
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=pi-", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("docker not found — is Docker installed?", file=sys.stderr)
        sys.exit(1)

    nums: set[int] = set()
    for name in result.stdout.strip().split():
        m = re.match(r"pi-(\d+)", name)
        if m:
            nums.add(int(m.group(1)))
    n = 1
    while n in nums:
        n += 1
    return n


def _temp_file(suffix: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="π-launcher-")
    os.close(fd)
    p = Path(path)
    atexit.register(lambda: p.unlink(missing_ok=True))
    return p


def generate_proj_fragment(n: int) -> Path:
    path = _temp_file(f".proj{n}.yml")
    path.write_text(
        "services:\n"
        "  pi:\n"
        "    volumes:\n"
        f"      - ${{PROJECT_PATH_{n}:?set PROJECT_PATH_{n}}}:${{PROJECT_PATH_{n}:?set PROJECT_PATH_{n}}}\n"
    )
    return path


def generate_override(
    main_path: str,
    additional_paths: list[str],
) -> Path:
    lines = [
        "services:",
        "  pi:",
        "    environment:",
    ]
    lines.append(f"      PROJECT_PATH_1: {main_path}")
    for i, path in enumerate(additional_paths, start=2):
        lines.append(f"      PROJECT_PATH_{i}: {path}")
    lines.append("")
    path = _temp_file(".override.yml")
    path.write_text("\n".join(lines))
    return path


def run_container(
    main_path: str,
    additional_projects: list[dict],
    override_path: Path,
    extra_fragments: list[Path],
    container_num: int,
    *,
    dry_run: bool,
) -> None:
    env = os.environ.copy()
    env["PROJECT_PATH_1"] = main_path
    for i, proj in enumerate(additional_projects, start=2):
        env[f"PROJECT_PATH_{i}"] = proj["workspaceFolders"][0]
    env["COMPOSE_FILE"] = ":".join(
        [str(COMPOSE_FILE_BASE)]
        + [str(f) for f in extra_fragments]
        + [str(override_path)]
    )

    name = f"pi-{container_num}"
    cmd = [
        "docker",
        "compose",
        "--project-directory",
        str(REPO_ROOT),
        "run",
        "--rm",
        "--remove-orphans",
        "--name",
        name,
        "pi",
    ]

    print(f"COMPOSE_FILE={env['COMPOSE_FILE']}")
    print(f"PROJECT_PATH_1={env['PROJECT_PATH_1']}")
    for i in range(2, len(additional_projects) + 2):
        print(f"PROJECT_PATH_{i}={env.get(f'PROJECT_PATH_{i}', '')}")
    print()
    if dry_run:
        print(f"--- override ({override_path}) ---")
        print(override_path.read_text())
        print("--- end override ---")
        print()
    print(" ".join(cmd))

    if dry_run:
        return

    subprocess.run(cmd, env=env, cwd=REPO_ROOT)


# ── TUI ──────────────────────────────────────────────────────────────────────


def _tui_draw_header(stdscr, container_num: int) -> None:
    h, w = stdscr.getmaxyx()
    title = f"π Launcher — container: π-{container_num} "
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_REVERSE)


def _tui_status(stdscr, text: str, color: int) -> None:
    h, w = stdscr.getmaxyx()
    stdscr.addstr(h - 1, 0, text.ljust(w)[: w - 1], color)


def _item_key(item: FlatItem) -> tuple:
    if item.kind == "ide":
        return ("ide", item.ide_index)
    if item.kind == "tree" and item.node is not None:
        return ("tree", str(item.node.path))
    return ("separator", id(item))


def _add_subtree(result: list[FlatItem], node: TreeNode, indent: int) -> None:
    item = FlatItem(kind="tree", label=node.name, indent=indent, node=node)
    result.append(item)
    if node.expanded:
        for child in node.children:
            _add_subtree(result, child, indent + 1)


def _rebuild_flat(source: list[FlatItem]) -> list[FlatItem]:
    result: list[FlatItem] = []
    for item in source:
        result.append(item)
        if item.kind == "tree" and item.node is not None and item.node.expanded:
            for child in item.node.children:
                _add_subtree(result, child, item.indent + 1)
    return result


def _tree_indicator(node: TreeNode) -> str:
    if node.expanded:
        return "[-]"
    if node.has_subdirs:
        return "[+]"
    return "[ ]"


def run_tui(
    projects: list[dict],
    tree_roots: list[TreeNode] | None = None,
    *,
    light_theme: bool = False,
) -> tuple[FlatItem | None, list[FlatItem]]:
    num = next_container_num()

    # Build source list (canonical items before expand/collapse)
    source: list[FlatItem] = []
    has_ide = len(projects) > 0
    has_tree = tree_roots is not None and len(tree_roots) > 0

    if has_ide:
        for i, proj in enumerate(projects):
            source.append(FlatItem(kind="ide", label="", indent=0, ide_index=i))
    if has_ide and has_tree:
        source.append(FlatItem(kind="separator", label="Открыты в IDE", indent=0))
    if has_tree:
        source.append(
            FlatItem(kind="separator", label="В базовой директории", indent=0)
        )
        for node in tree_roots:
            source.append(FlatItem(kind="tree", label=node.name, indent=0, node=node))

    flat_items = _rebuild_flat(source)

    # Selection state
    main_key: tuple | None = None
    additional_keys: set[tuple] = set()
    cursor = 0
    viewport_offset = 0
    status_msg = ""
    status_ttl = 0
    last_enter_time = 0.0

    # Initialize: first item as main
    if flat_items:
        first = flat_items[0]
        if first.kind != "separator":
            main_key = _item_key(first)
            cursor = 0
        else:
            # Skip separators for initial selection
            for idx, item in enumerate(flat_items):
                if item.kind != "separator":
                    main_key = _item_key(item)
                    cursor = idx
                    break

    def _current_main_idx() -> int | None:
        if main_key is None:
            return None
        for idx, item in enumerate(flat_items):
            if _item_key(item) == main_key:
                return idx
        return None

    def _current_additional_set() -> set[int]:
        result: set[int] = set()
        for idx, item in enumerate(flat_items):
            if _item_key(item) in additional_keys:
                result.add(idx)
        return result

    def _selectable_indices() -> list[int]:
        return [i for i, item in enumerate(flat_items) if item.kind != "separator"]

    def _clamp_cursor() -> None:
        nonlocal cursor
        sel = _selectable_indices()
        if not sel:
            return
        if cursor not in sel:
            # Find nearest selectable
            cursor = min(sel, key=lambda i: abs(i - cursor))

    def _ensure_cursor_visible(list_height: int) -> None:
        nonlocal viewport_offset, cursor
        if not flat_items:
            viewport_offset = 0
            return
        # Shift viewport so cursor stays within the visible window
        if cursor < viewport_offset:
            viewport_offset = cursor
        elif cursor >= viewport_offset + list_height:
            viewport_offset = cursor - list_height + 1
        # Clamp to valid range
        max_offset = max(0, len(flat_items) - list_height)
        if viewport_offset > max_offset:
            viewport_offset = max_offset
        if viewport_offset < 0:
            viewport_offset = 0

    def draw(stdscr) -> tuple[FlatItem | None, list[FlatItem]]:
        nonlocal \
            main_key, \
            additional_keys, \
            cursor, \
            viewport_offset, \
            status_msg, \
            status_ttl, \
            last_enter_time
        nonlocal flat_items

        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        if light_theme:
            curses.init_pair(1, curses.COLOR_BLUE, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)
        else:
            curses.init_pair(1, curses.COLOR_YELLOW, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLUE)

        COLOR_MAIN = curses.color_pair(1) | curses.A_BOLD
        COLOR_EXTRA = curses.color_pair(2)
        COLOR_STATUS = curses.color_pair(3)
        COLOR_DIM = curses.A_DIM if hasattr(curses, "A_DIM") else curses.A_NORMAL

        while True:
            h, w = stdscr.getmaxyx()
            if h < 5:
                stdscr.clear()
                stdscr.addstr(0, 0, "terminal too small", curses.A_BOLD)
                stdscr.refresh()
                if stdscr.getch() == ord("q"):
                    sys.exit(1)
                continue

            stdscr.erase()
            _tui_draw_header(stdscr, num)

            # If the very first item is a separator, skip the blank row
            list_start = 1 if (flat_items and flat_items[0].kind == "separator") else 2
            list_height = h - 3
            sel_marker_col = w - 4  # right-aligned selection marker column

            # Ensure viewport keeps cursor visible (handles resize too)
            _ensure_cursor_visible(list_height)

            main_idx = _current_main_idx()
            additional_set = _current_additional_set()

            visible_end = min(len(flat_items), viewport_offset + list_height)
            for vi in range(viewport_offset, visible_end):
                item = flat_items[vi]
                row = list_start + (vi - viewport_offset)

                is_main = vi == main_idx
                is_additional = vi in additional_set
                is_cursor = vi == cursor

                if item.kind == "separator":
                    # Pseudographics separator
                    if has_ide and has_tree:
                        if item.label == "Открыты в IDE":
                            sep = f" ───═══ {item.label}: ═══───"
                        else:
                            sep = f" ───═══ {item.label} ═══───"
                    else:
                        sep = f" ───═══ {item.label} ═══───"
                    line = sep.ljust(w)[:w]
                    attr = COLOR_DIM
                    if is_cursor:
                        attr |= curses.A_REVERSE
                    stdscr.addstr(row, 0, line, attr)
                    continue

                # Build display line
                sel_marker = "★" if is_main else ("✓" if is_additional else " ")

                if item.kind == "ide" and item.ide_index is not None:
                    proj = projects[item.ide_index]
                    ide = proj["ideName"]
                    port_str = str(proj["port"])
                    ws_path = (
                        proj["workspaceFolders"][0] if proj["workspaceFolders"] else "?"
                    )
                    suffix = f"  :{port_str}  {ide}"
                    prefix = "  "
                    available = w - len(prefix) - len(suffix) - 4
                    if available < 10:
                        available = 10
                    if len(ws_path) > available:
                        ws_path = "..." + ws_path[-(available - 3) :]
                    left = prefix + ws_path
                    right = f"{sel_marker}  {suffix}"
                    right_aligned = (
                        right.rjust(w - len(left))
                        if len(left) + len(right) <= w
                        else right
                    )
                    line = left + right_aligned[len(left) :]
                elif item.kind == "tree":
                    indent_str = "    " * item.indent
                    indicator = _tree_indicator(item.node) if item.node else "[ ]"
                    left = f"{indent_str}{indicator} {item.label}/"
                    right_marker = f" {sel_marker}"
                    # Pad to sel_marker_col
                    if len(left) < sel_marker_col:
                        line = left + " " * (sel_marker_col - len(left)) + right_marker
                    else:
                        line = left + right_marker
                else:
                    line = f"  {item.label}"

                line = line[:w]

                if is_main:
                    attr = COLOR_MAIN
                elif is_additional:
                    attr = COLOR_EXTRA
                else:
                    attr = curses.A_NORMAL
                if is_cursor:
                    attr |= curses.A_REVERSE
                stdscr.addstr(row, 0, line, attr)

            # Status bar
            if status_ttl > 0:
                status_ttl -= 1
            else:
                status_msg = ""

            if status_msg:
                _tui_status(stdscr, f"  {status_msg}", COLOR_STATUS)
            else:
                main_name = "?"
                if main_idx is not None and main_idx < len(flat_items):
                    mi = flat_items[main_idx]
                    if mi.kind == "ide" and mi.ide_index is not None:
                        p = projects[mi.ide_index]
                        main_name = (
                            Path(p["workspaceFolders"][0]).name
                            if p["workspaceFolders"]
                            else "?"
                        )
                    elif mi.kind == "tree":
                        main_name = mi.label
                footer = (
                    f"  Space:cycle  Enter:main  dbl-Enter/F5/r:launch"
                    f"  ←/→:collapse/expand  q:quit"
                    f"    main: {main_name}"
                    f"  extra: {len(additional_keys)}"
                )
                _tui_status(stdscr, footer, COLOR_STATUS)

            stdscr.refresh()
            key = stdscr.getch()

            if key in (ord("q"), 27):
                sys.exit(0)
            elif key in (curses.KEY_UP, ord("k")):
                sel = _selectable_indices()
                if sel:
                    try:
                        cur_pos = sel.index(cursor)
                        if cur_pos > 0:
                            cursor = sel[cur_pos - 1]
                    except ValueError:
                        cursor = sel[-1] if sel else 0
            elif key in (curses.KEY_DOWN, ord("j")):
                sel = _selectable_indices()
                if sel:
                    try:
                        cur_pos = sel.index(cursor)
                        if cur_pos < len(sel) - 1:
                            cursor = sel[cur_pos + 1]
                    except ValueError:
                        cursor = sel[0]
            elif key == curses.KEY_RIGHT:
                item = flat_items[cursor] if cursor < len(flat_items) else None
                if item is not None and item.kind == "tree" and item.node is not None:
                    node = item.node
                    if node.has_subdirs and not node.expanded:
                        node.children = build_tree(node.path, node.depth + 1)
                        node.expanded = True
                        flat_items = _rebuild_flat(source)
                        _clamp_cursor()
            elif key == curses.KEY_LEFT:
                item = flat_items[cursor] if cursor < len(flat_items) else None
                if item is not None and item.kind == "tree" and item.node is not None:
                    node = item.node
                    if node.expanded:
                        # Find descendant range in flat_items
                        start_idx = cursor
                        end_idx = cursor
                        for j in range(cursor + 1, len(flat_items)):
                            fj = flat_items[j]
                            if fj.kind == "tree" and fj.indent > node.depth:
                                end_idx = j
                            else:
                                break
                        node.expanded = False
                        flat_items = _rebuild_flat(source)
                        # If cursor was inside the subtree, jump to parent
                        if cursor > start_idx and cursor <= end_idx:
                            # Find parent in rebuilt flat
                            for idx, fi in enumerate(flat_items):
                                if fi.kind == "tree" and fi.node is node:
                                    cursor = idx
                                    break
                        _clamp_cursor()
            elif key in (curses.KEY_ENTER, 10, 13):
                item = flat_items[cursor] if cursor < len(flat_items) else None
                if item is None or item.kind == "separator":
                    continue
                now = time.monotonic()
                if now - last_enter_time < 0.5 and main_key is not None:
                    # Launch
                    main_idx_final = _current_main_idx()
                    if main_idx_final is not None:
                        main_item = flat_items[main_idx_final]
                        additional = [
                            flat_items[i]
                            for i in sorted(_current_additional_set())
                            if flat_items[i].kind != "separator"
                        ]
                        return main_item, additional
                last_enter_time = now
                # Single Enter: set as main
                main_key = _item_key(item)
                additional_keys.discard(_item_key(item))
            elif key in (curses.KEY_F5, ord("r")):
                if main_key is not None:
                    main_idx_final = _current_main_idx()
                    if main_idx_final is not None:
                        main_item = flat_items[main_idx_final]
                        additional = [
                            flat_items[i]
                            for i in sorted(_current_additional_set())
                            if flat_items[i].kind != "separator"
                        ]
                        return main_item, additional
            elif key == ord(" "):
                item = flat_items[cursor] if cursor < len(flat_items) else None
                if item is None or item.kind == "separator":
                    continue
                ik = _item_key(item)
                if ik == main_key:
                    # main -> not selected
                    main_key = None
                    additional_keys.discard(ik)
                elif ik in additional_keys:
                    if main_key is not None:
                        # additional -> main (swap)
                        additional_keys.discard(ik)
                        if main_key is not None:
                            additional_keys.add(main_key)
                        main_key = ik
                    else:
                        # additional -> not selected
                        additional_keys.discard(ik)
                else:
                    if main_key is not None:
                        # not selected -> additional
                        additional_keys.add(ik)
                    else:
                        # not selected -> main
                        main_key = ik
                        additional_keys.discard(ik)
            elif key == curses.KEY_RESIZE:
                pass

    return curses.wrapper(draw)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tui",
        "--gui",
        action="store_true",
        help="Launch interactive TUI for project selection",
    )
    parser.add_argument(
        "--no-forward", action="store_true", help="Skip socat port forwarding"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print command without executing"
    )
    parser.add_argument(
        "--light", action="store_true", help="Light theme (default: dark)"
    )
    parser.add_argument(
        "--base-project-dir",
        help="Root directory for filesystem tree view (overrides .env BASE_PROJECT_DIR)",
    )
    args = parser.parse_args()

    # Resolve base-project-dir: CLI > .env > None
    env_config = load_env()
    base_project_dir = args.base_project_dir or env_config.get("BASE_PROJECT_DIR")
    if base_project_dir is not None:
        base_project_dir = os.path.expanduser(base_project_dir)

    projects = []

    # Fallback: if no IDE projects and no base dir, use home directory
    if not projects and base_project_dir is None:
        base_project_dir = str(Path.home())

    # Build tree roots
    tree_roots: list[TreeNode] | None = None
    if base_project_dir is not None:
        base_path = Path(base_project_dir)
        if base_path.is_dir():
            tree_roots = build_tree(base_path)
        else:
            print(
                f"base-project-dir '{base_project_dir}' does not exist or is not readable,"
                f" falling back to home",
                file=sys.stderr,
            )
            tree_roots = build_tree(Path.home())

    if not projects and tree_roots is None:
        print(
            "No live IDE projects found and no base directory available",
            file=sys.stderr,
        )
        sys.exit(1)

    main_item, additional_items = run_tui(projects, tree_roots, light_theme=args.light)

    if main_item is None:
        print("No project selected", file=sys.stderr)
        sys.exit(1)

    # Build launch data from selected items
    main_path: str = ""
    additional_projects: list[dict] = []
    additional_paths: list[str] = []

    if main_item.kind == "tree" and main_item.node is not None:
        main_path = str(main_item.node.path)

    if not main_path:
        print("Main project has no path", file=sys.stderr)
        sys.exit(1)

    for item in additional_items:
        if item.kind == "tree" and item.node is not None:
            additional_projects.append(
                {"workspaceFolders": [str(item.node.path)], "port": 0, "rawContent": ""}
            )
            additional_paths.append(str(item.node.path))

    extra_fragments = [
        generate_proj_fragment(n) for n in range(2, len(additional_paths) + 2)
    ]
    override_path = generate_override(main_path, additional_paths)

    container_num = next_container_num()
    try:
        run_container(
            main_path,
            additional_projects,
            override_path,
            extra_fragments,
            container_num,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print()
        sys.exit(130)


if __name__ == "__main__":
    main()
