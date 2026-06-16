#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///

"""Launch Claude Code Docker container with IDE integration.

Discovers IDE projects from ~/.claude/ide/*.lock files, provides a TUI
for selecting main and additional projects, then runs docker compose
with the appropriate mounts, env vars, and port forwarding.

Usage:
  uv run launch-claude.py                   # auto-detect main project, no TUI
  uv run launch-claude.py --tui             # interactive project selection
  uv run launch-claude.py --dry-run         # print command, don't run
  uv run launch-claude.py --light           # light theme (with --tui)
  uv run launch-claude.py --no-forward      # skip socat port forwarding
"""

from __future__ import annotations

import argparse
import atexit
import curses
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
COMPOSE_FILE_BASE = REPO_ROOT / "docker-compose.yml"


def discover_projects() -> list[dict]:
    ide_dir = Path.home() / ".claude" / "ide"
    if not ide_dir.is_dir():
        return []

    projects = []
    for lock_file in sorted(ide_dir.glob("*.lock")):
        port_str = lock_file.stem
        try:
            port = int(port_str)
        except ValueError:
            continue

        try:
            raw = lock_file.read_text()
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            continue

        if data.get("transport") != "ws":
            continue

        pid = data.get("pid")
        if pid is None:
            continue

        try:
            os.kill(pid, 0)
        except OSError:
            continue

        projects.append(
            {
                "port": port,
                "pid": pid,
                "workspaceFolders": data.get("workspaceFolders", []),
                "authToken": data.get("authToken", ""),
                "ideName": data.get("ideName", "unknown"),
                "rawContent": raw,
            }
        )

    return projects


def resolve_main_project(projects: list[dict]) -> int | None:
    """Pick the main project index from CLAUDE_CODE_SSE_PORT env var.
    Returns the index if a matching live project is found, None otherwise.
    """
    target_port = os.environ.get("CLAUDE_CODE_SSE_PORT")
    if target_port is None:
        return None
    try:
        target_port_int = int(target_port)
    except ValueError:
        return None
    for i, proj in enumerate(projects):
        if proj["port"] == target_port_int:
            return i
    return None


def next_container_num() -> int:
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=claude-", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("docker not found — is Docker installed?", file=sys.stderr)
        sys.exit(1)

    nums: set[int] = set()
    for name in result.stdout.strip().split():
        m = re.match(r"claude-(\d+)", name)
        if m:
            nums.add(int(m.group(1)))
    n = 1
    while n in nums:
        n += 1
    return n


def _temp_file(suffix: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="claude-launcher-")
    os.close(fd)
    p = Path(path)
    atexit.register(lambda: p.unlink(missing_ok=True))
    return p


def generate_proj_fragment(n: int) -> Path:
    path = _temp_file(f".proj{n}.yml")
    path.write_text(
        "services:\n"
        "  claude:\n"
        "    volumes:\n"
        f"      - ${{PROJECT_PATH_{n}:?set PROJECT_PATH_{n}}}:${{PROJECT_PATH_{n}:?set PROJECT_PATH_{n}}}\n"
    )
    return path


def generate_init_script(
    projects: list[dict], all_ports: list[int], *, no_forward: bool
) -> Path:
    """Shell script that creates IDE lock files and starts socat port forwarding."""
    lines = ["#!/bin/bash", "mkdir -p -m 0700 /home/dev/.claude/ide || exit 1"]
    for proj in projects:
        content = proj.get("rawContent", "")
        if not content:
            continue
        port = proj["port"]
        lines.append(f"cat > /home/dev/.claude/ide/{port}.lock << 'LOCKEOF'")
        lines.append(content)
        lines.append("LOCKEOF")
        # Host PID is meaningless inside the container PID namespace.
        # Replace it with $$ (the shell's PID) so the CLI's liveness check passes.
        lines.append(
            f'sed -i "s/\\"pid\\":[0-9]*/\\"pid\\":$$/" '
            f"/home/dev/.claude/ide/{port}.lock"
        )
        lines.append(f"chmod 0600 /home/dev/.claude/ide/{port}.lock")
    if not no_forward:
        ports_str = " ".join(str(p) for p in all_ports)
        lines.append(f"for PORT in {ports_str}; do")
        lines.append(
            '  socat TCP-LISTEN:"$PORT",fork,bind=127.0.0.1 TCP:host.docker.internal:"$PORT" &'
        )
        lines.append("done")
    lines.append("exec claude")
    path = _temp_file(".claude-init.sh")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o644)
    return path


def generate_main_override(
    main_project: dict,
    additional_paths: list[str],
    init_script_path: Path,
) -> Path:
    lines = [
        "services:",
        "  claude:",
        "    environment:",
        f'      CLAUDE_CODE_SSE_PORT: "{main_project["port"]}"',
        '      ENABLE_IDE_INTEGRATION: "true"',
    ]
    for i, path in enumerate(additional_paths, start=2):
        lines.append(f"      PROJECT_PATH_{i}: {path}")

    # tmpfs for ide/: container-local, not mounted from host — preserves Zed's 0700/0600
    lines.append("    volumes:")
    lines.append("      - type: tmpfs")
    lines.append("        target: /home/dev/.claude/ide")
    lines.append(f"      - {init_script_path}:/usr/local/bin/claude-init.sh:ro")

    lines.append("    command:")
    lines.append('      - "bash"')
    lines.append('      - "/usr/local/bin/claude-init.sh"')
    lines.append("")

    path = _temp_file(".override.yml")
    path.write_text("\n".join(lines))
    return path


def run_container(
    main_project: dict,
    additional_projects: list[dict],
    override_path: Path,
    extra_fragments: list[Path],
    container_num: int,
    *,
    dry_run: bool,
) -> None:
    env = os.environ.copy()
    env["PROJECT_PATH_1"] = main_project["workspaceFolders"][0]
    for i, proj in enumerate(additional_projects, start=2):
        env[f"PROJECT_PATH_{i}"] = proj["workspaceFolders"][0]
    env["COMPOSE_FILE"] = ":".join(
        [str(COMPOSE_FILE_BASE)]
        + [str(f) for f in extra_fragments]
        + [str(override_path)]
    )

    name = f"claude-{container_num}"
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
        "claude",
    ]

    print(f"COMPOSE_FILE={env['COMPOSE_FILE']}")
    print(f"PROJECT_PATH_1={env['PROJECT_PATH_1']}")
    for i in range(2, len(additional_projects) + 2):
        print(f"PROJECT_PATH_{i}={env.get(f'PROJECT_PATH_{i}', '')}")
    print(f"CLAUDE_CODE_SSE_PORT={main_project['port']}")
    print("ENABLE_IDE_INTEGRATION=true")
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
    title = f" Claude Code Launcher — container: claude-{container_num} "
    stdscr.addstr(0, max(0, (w - len(title)) // 2), title, curses.A_REVERSE)


def _tui_format_line(
    proj: dict,
    is_main: bool,
    is_additional: bool,
    cursor_on: bool,
    width: int,
    color_main: int,
    color_extra: int,
) -> tuple[str, int]:
    if is_main:
        prefix = " [★] "
    elif is_additional:
        prefix = " [✓] "
    else:
        prefix = " [ ] "

    ide = proj["ideName"]
    port_str = str(proj["port"])
    ws_path = proj["workspaceFolders"][0] if proj["workspaceFolders"] else "?"
    suffix = f"  :{port_str}  {ide}"
    available = width - len(prefix) - len(suffix) - 2
    if available < 10:
        available = 10
    if len(ws_path) > available:
        ws_path = "..." + ws_path[-(available - 3) :]

    line = (
        prefix
        + ws_path
        + " " * max(1, width - len(prefix) - len(ws_path) - len(suffix))
        + suffix
    )
    if is_main:
        attr = color_main
    elif is_additional:
        attr = color_extra
    else:
        attr = curses.A_NORMAL
    if cursor_on:
        attr |= curses.A_REVERSE
    return line[:width], attr


def _tui_status(stdscr, text: str, color: int) -> None:
    h, w = stdscr.getmaxyx()
    stdscr.addstr(h - 1, 0, text.ljust(w)[: w - 1], color)


def run_tui(projects: list[dict], *, light_theme: bool) -> tuple[int, set[int]]:
    main_idx = 0
    additional: set[int] = set()
    cursor = 0
    num = next_container_num()
    status_msg = ""
    status_ttl = 0  # ticks until status clears
    last_enter_time = 0.0

    def draw(stdscr) -> tuple[int, set[int]]:
        nonlocal main_idx, cursor, status_msg, status_ttl, last_enter_time

        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        if light_theme:
            curses.init_pair(1, curses.COLOR_BLUE, -1)  # main
            curses.init_pair(2, curses.COLOR_GREEN, -1)  # extra
            curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_CYAN)  # status
        else:
            curses.init_pair(1, curses.COLOR_YELLOW, -1)  # main
            curses.init_pair(2, curses.COLOR_GREEN, -1)  # extra
            curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLUE)  # status

        COLOR_MAIN = curses.color_pair(1) | curses.A_BOLD
        COLOR_EXTRA = curses.color_pair(2)
        COLOR_STATUS = curses.color_pair(3)

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

            list_start = 2
            list_height = h - 3

            for i, proj in enumerate(projects):
                row = list_start + i
                if row >= list_start + list_height:
                    break

                is_main = i == main_idx
                is_additional = (i in additional) and not is_main
                line, attr = _tui_format_line(
                    proj,
                    is_main,
                    is_additional,
                    cursor == i,
                    w,
                    COLOR_MAIN,
                    COLOR_EXTRA,
                )
                stdscr.addstr(row, 0, line, attr)

            # Status bar
            if status_ttl > 0:
                status_ttl -= 1
            else:
                status_msg = ""

            if status_msg:
                _tui_status(stdscr, f"  {status_msg}", COLOR_STATUS)
            else:
                main_path = (
                    projects[main_idx]["workspaceFolders"][0]
                    if projects[main_idx]["workspaceFolders"]
                    else "?"
                )
                footer = (
                    f"  Space:cycle  Enter:main  dbl-Enter/F5/r:launch  q:quit"
                    f"    main: {Path(main_path).name}"
                    f"  extra: {len(additional)}"
                )
                _tui_status(stdscr, footer, COLOR_STATUS)

            stdscr.refresh()
            key = stdscr.getch()

            if key in (ord("q"), 27):  # q or Esc
                sys.exit(0)
            elif key in (curses.KEY_UP, ord("k")):
                cursor = (cursor - 1) % len(projects)
            elif key in (curses.KEY_DOWN, ord("j")):
                cursor = (cursor + 1) % len(projects)
            elif key in (curses.KEY_ENTER, 10, 13):
                now = time.monotonic()
                if now - last_enter_time < 0.5 and main_idx >= 0:
                    return main_idx, additional
                last_enter_time = now
                # Single Enter: set focused project as main
                if cursor != main_idx:
                    if main_idx >= 0:
                        additional.discard(cursor)
                        additional.add(main_idx)
                    else:
                        additional.discard(cursor)
                    main_idx = cursor
            elif key in (curses.KEY_F5, ord("r")):
                if main_idx >= 0:
                    return main_idx, additional
            elif key == ord(" "):
                if cursor == main_idx:
                    # main -> not selected
                    main_idx = -1
                    additional.discard(cursor)
                elif cursor in additional:
                    if main_idx >= 0:
                        # additional -> main (swap)
                        additional.discard(cursor)
                        additional.add(main_idx)
                        main_idx = cursor
                    else:
                        # additional -> not selected
                        additional.discard(cursor)
                else:
                    if main_idx >= 0:
                        # not selected -> additional (main already taken)
                        additional.add(cursor)
                    else:
                        # not selected -> main
                        main_idx = cursor
                        additional.discard(cursor)
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
    args = parser.parse_args()

    projects = discover_projects()
    if not projects:
        print("No live IDE projects found in ~/.claude/ide/", file=sys.stderr)
        sys.exit(1)

    additional_indices: set[int] = set()
    if args.tui:
        main_idx, additional_indices = run_tui(projects, light_theme=args.light)
    else:
        main_idx = resolve_main_project(projects)
        if main_idx is None:
            if sys.stdin.isatty():
                main_idx, additional_indices = run_tui(projects, light_theme=args.light)
            else:
                # piped stdin (e.g. dry-run): pick the first live project
                main_idx = 0

    main_project = projects[main_idx]
    additional_projects = [projects[i] for i in sorted(additional_indices)]

    if not main_project.get("workspaceFolders"):
        print("Main project has no workspace folders", file=sys.stderr)
        sys.exit(1)

    extra_fragments: list[Path] = []
    for n in range(2, len(additional_projects) + 2):
        extra_fragments.append(generate_proj_fragment(n))

    all_ports = [main_project["port"]] + [p["port"] for p in additional_projects]
    all_selected = [main_project] + additional_projects
    init_script_path = generate_init_script(
        all_selected, all_ports, no_forward=args.no_forward
    )
    override_path = generate_main_override(
        main_project,
        [p["workspaceFolders"][0] for p in additional_projects],
        init_script_path,
    )

    # Append override at end of COMPOSE_FILE chain; run_container sets COMPOSE_FILE via env

    container_num = next_container_num()
    try:
        run_container(
            main_project,
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
