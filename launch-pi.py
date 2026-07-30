#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///

"""Launch π Docker container with IDE integration.

Provides a TUI for selecting main and additional projects,
then runs docker compose (via versions.py compose for resolved
toolchain variables) with the appropriate mounts, env vars,
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
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from docker.tui import FlatItem, TreeNode, build_tree, run_tui

REPO_ROOT = Path(__file__).resolve().parent
COMPOSE_FILE_BASE = REPO_ROOT / "docker-compose.yml"
COMPOSE_FILE_RUNTIME = REPO_ROOT / "docker-compose.runtime.yml"


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
        f"    working_dir: {main_path}",
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
    mount_main_path: str,
    additional_projects: list[dict],
    override_path: Path,
    extra_fragments: list[Path],
    container_num: int,
    *,
    dry_run: bool,
) -> None:
    env = os.environ.copy()
    env["PROJECT_PATH_1"] = mount_main_path
    for i, proj in enumerate(additional_projects, start=2):
        env[f"PROJECT_PATH_{i}"] = proj["workspaceFolders"][0]
    env["COMPOSE_FILE"] = ":".join(
        [str(COMPOSE_FILE_BASE), str(COMPOSE_FILE_RUNTIME)]
        + [str(f) for f in extra_fragments]
        + [str(override_path)]
    )

    name = f"pi-{container_num}"
    cmd = [
        "python3",
        "docker/versions.py",
        "compose",
        "run",
        "--rm",
        "--remove-orphans",
        "--name",
        name,
        "pi",
    ]

    print(f"COMPOSE_FILE={env['COMPOSE_FILE']}")
    print(f"PROJECT_PATH_1={env['PROJECT_PATH_1']}")
    if mount_main_path != main_path:
        print(f"working_dir={main_path}")
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


# ── Entry point ───────────────────────────────────────────────────────────────


def _path_contains(parent: str, child: str) -> bool:
    parent_path = Path(parent).resolve()
    child_path = Path(child).resolve()
    return parent_path != child_path and child_path.is_relative_to(parent_path)


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

    main_item, additional_items = run_tui(projects, tree_roots, light_theme=args.light, container_num=next_container_num())

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

    mount_main_path = main_path
    mounted_additional_paths = additional_paths
    containing_additional_paths = [
        path for path in additional_paths if _path_contains(path, main_path)
    ]
    if containing_additional_paths:
        mount_main_path = min(
            containing_additional_paths, key=lambda path: len(Path(path).resolve().parts)
        )
        mounted_additional_paths = [
            path for path in additional_paths if path != mount_main_path
        ]
        additional_projects = [
            {"workspaceFolders": [path], "port": 0, "rawContent": ""}
            for path in mounted_additional_paths
        ]

    extra_fragments = [
        generate_proj_fragment(n) for n in range(2, len(mounted_additional_paths) + 2)
    ]
    override_path = generate_override(main_path, mounted_additional_paths)

    container_num = next_container_num()
    try:
        run_container(
            main_path,
            mount_main_path,
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
