"""
Importable thin facade for the Pi Docker constructor.

Primary commands: ``build``, ``run``, ``check-updates``.
Auxiliary commands: ``validate``, ``show``, ``doctor``, ``verify``.

The facade owns only argument parsing, input validation, a generic
rendering layer, and exit-code mapping.  All domain behaviour is
accessed through an injectable ``CommandDispatcher`` protocol.

Read-only domain logic (validate, show, check-updates) is delegated to
``docker.versioning.readonly_service`` — the facade calls a single
``dispatch()`` entry point after resolving the inventory path.

This module is a pure importable package module — it **never** mutates
``sys.path``.  Direct execution is handled by the minimal bootstrap in
``docker/docker-constructor.py``.

Usage (imported)::

    from docker.constructor_cli import main
    exit_code = main(["validate", "--scope", "build"])

Usage (via executable wrapper)::

    docker/docker-constructor.py validate [--scope build|runtime|all]
"""

from __future__ import annotations

import argparse
import json as _json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from docker.versioning.dispatch_types import CommandResult, ExitKind
from docker.versioning.immutable import deep_freeze

_REPO_ROOT = Path(__file__).resolve().parent.parent


_EXIT_CODES: dict[ExitKind, int] = {
    ExitKind.SUCCESS: 0,
    ExitKind.POLICY: 1,
    ExitKind.CLI: 2,
    ExitKind.CONFIG: 3,
    ExitKind.OPERATIONAL: 4,
}


# ═══════════════════════════════════════════════════════════════════════
# Immutable dispatch boundary
# ═══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CommandRequest:
    """Parsed argument bundle passed to the dispatcher.

    All fields are deeply immutable — ``command_args`` is stored as
    a ``MappingProxyType`` so that callers cannot mutate it after
    construction.
    """

    command: str
    inventory: str | None
    output: str          # "text" | "json"
    verbose: bool
    color: str           # "auto" | "always" | "never"
    command_args: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Always deep-freeze — even a pre-frozen proxy may wrap mutable children
        object.__setattr__(
            self,
            "command_args",
            deep_freeze(self.command_args),
        )




class CommandDispatcher(Protocol):
    """Domain boundary — every subcommand flows through ``execute``."""

    def execute(self, command: str, request: CommandRequest) -> CommandResult:
        ...


# ═══════════════════════════════════════════════════════════════════════
# Inventory resolution & domain dispatch
# ═══════════════════════════════════════════════════════════════════════


def _resolve_inventory_path(request: CommandRequest) -> Path:
    """Resolve the inventory path from request or repo root.

    Explicit ``--inventory`` paths are accepted regardless of basename.
    The default is ``docker-constructor.toml`` in the repository root
    (parent of the ``docker/`` directory containing this module).
    """
    if request.inventory:
        return Path(request.inventory)
    return _REPO_ROOT / "docker-constructor.toml"


def _real_dispatcher(
    command: str, request: CommandRequest,
) -> CommandResult:
    """Thin facade wrapper that delegates to the internal services.

    Read-only commands (validate, show, check-updates) are routed to
    ``docker.versioning.readonly_service``.
    Build and doctor commands are routed to
    ``docker.versioning.build_orchestration``.
    """
    # Commands that do not require an inventory path
    if command == "doctor":
        from docker.versioning.build_orchestration import dispatch as orch_dispatch
        from pathlib import Path
        return orch_dispatch(
            Path("."),  # doctor does not read inventory
            command,
            command_args=request.command_args,
        )

    try:
        inv_path = _resolve_inventory_path(request)
    except OSError as exc:
        return CommandResult(
            exit_kind=ExitKind.CONFIG,
            message=f"cannot resolve inventory path: {exc}",
        )

    if command == "build":
        from docker.versioning.build_orchestration import dispatch as orch_dispatch
        return orch_dispatch(
            inv_path, command, command_args=request.command_args,
        )

    from docker.versioning.readonly_service import dispatch
    return dispatch(inv_path, command, command_args=request.command_args)


# ═══════════════════════════════════════════════════════════════════════
# Generic rendering (consumes CommandResult, not domain objects)
# ═══════════════════════════════════════════════════════════════════════

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_RED = "\x1b[31m"
_YELLOW = "\x1b[33m"
_GREEN = "\x1b[32m"


def _use_colour(color: str, *, stream_is_tty: bool) -> bool:
    if color == "always":
        return True
    if color == "never":
        return False
    return stream_is_tty  # "auto"


def _coloured(text: str, code: str, color: str, *,
              stream_is_tty: bool) -> str:
    if not _use_colour(color, stream_is_tty=stream_is_tty):
        return text
    return f"{code}{text}{_RESET}"


def _render(
    command: str,
    result: CommandResult,
    *,
    fmt: str,
    color: str,
    verbose: bool,
    stdout_is_tty: bool,
    stderr_is_tty: bool,
) -> tuple[str, str]:
    """Render a CommandResult to (stdout_text, stderr_text).

    Channel rules:
    * JSON mode — everything on stdout, machine-readable.
    * Text mode:
      - SUCCESS / POLICY → stdout (semantic output).
      - CLI / CONFIG / OPERATIONAL → stderr (diagnostics).
      - When both *data* and *message* are present, both are rendered.
      - *debug* detail is only appended to stderr when ``verbose`` is
        true, regardless of exit kind.
    """
    _ERROR_KINDS = {ExitKind.CLI, ExitKind.CONFIG, ExitKind.OPERATIONAL}
    is_error = result.exit_kind in _ERROR_KINDS

    out_lines: list[str] = []
    err_lines: list[str] = []

    if fmt == "json":
        payload: dict[str, Any] = {
            "command": command,
            "status": result.exit_kind.value,
        }
        if result.data is not None:
            payload["data"] = result.data
        if result.message is not None:
            payload["message"] = result.message
        out_lines.append(_json.dumps(payload, indent=2, sort_keys=True,
                                     default=str))
    else:
        # ── text mode ────────────────────────────────────────────
        level = result.exit_kind.value.upper()
        code_map = {
            ExitKind.SUCCESS: _GREEN,
            ExitKind.POLICY: _YELLOW,
            ExitKind.CLI: _RED,
            ExitKind.CONFIG: _RED,
            ExitKind.OPERATIONAL: _RED,
        }
        code = code_map.get(result.exit_kind, _RESET)
        # Colour is resolved against the *target* stream's tty state
        tty = stderr_is_tty if is_error else stdout_is_tty
        prefix = _coloured(f"[{level}]", code, color, stream_is_tty=tty)

        target: list[str] = err_lines if is_error else out_lines

        # Render message and data — both when present
        if result.message:
            target.append(f"{prefix} {result.message}")
        if result.data is not None:
            rendered_data = str(result.data)
            if result.message:
                target.append(f"       data: {rendered_data}")
            else:
                target.append(f"{prefix} {rendered_data}")
        if not result.message and result.data is None:
            target.append(prefix)

    # Debug detail always to stderr, regardless of exit kind
    if verbose and result.debug:
        err_lines.append(f"[debug] {result.debug}")

    return "\n".join(out_lines), "\n".join(err_lines)


# ═══════════════════════════════════════════════════════════════════════
# Parser construction
# ═══════════════════════════════════════════════════════════════════════

def _add_global_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--inventory",
        default=None,
        metavar="PATH",
        help="Path to docker-constructor.toml (default: docker-constructor.toml"
             " in repo root)",
    )
    parser.add_argument(
        "--output",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Increase output verbosity",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colour output policy (default: auto)",
    )


def _dispatch_command(
    args: argparse.Namespace,
    *,
    dispatcher: CommandDispatcher,
) -> CommandResult:
    """Build a CommandRequest from parsed args and invoke the dispatcher."""
    # Collect command-owned arguments into command_args
    cmd_args: dict[str, object] = {}
    for attr in vars(args):
        if attr in ("command", "func", "inventory", "output", "verbose",
                     "color"):
            continue
        value = getattr(args, attr)
        # Normalise overrides: raw PATH=VALUE list → parsed dict
        if attr == "overrides" and isinstance(value, list):
            from docker.versioning.readonly_service import _parse_overrides
            try:
                value = _parse_overrides(value)
            except ValueError:
                # Pass raw so the handler can surface a CLI error
                pass
        cmd_args[attr] = value

    request = CommandRequest(
        command=args.command,
        inventory=args.inventory,
        output=args.output,
        verbose=args.verbose,
        color=args.color,
        command_args=cmd_args,
    )
    execute = dispatcher.execute if hasattr(dispatcher, "execute") else dispatcher
    return execute(args.command, request)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docker/docker-constructor.py",
        description="Pi Docker constructor — build, run, and inspect"
                    " the Pi container image.",
    )
    _add_global_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    # --- validate ---
    p_val = sub.add_parser("validate", help="Validate docker-constructor.toml")
    p_val.add_argument(
        "--scope",
        choices=("build", "runtime", "all"),
        default="all",
        help="Which sections to validate (default: all)",
    )
    p_val.set_defaults(func=_dispatch_command)

    # --- build (parser only; handler in Stage 9) ---
    p_build = sub.add_parser("build", help="Build the Pi container image")
    p_build.add_argument(
        "--platform",
        default="linux-amd64",
        help="Target platform (default: linux-amd64)",
    )
    p_build.add_argument(
        "--tag",
        default=None,
        help="Override the image tag",
    )
    p_build.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the build vector without executing",
    )
    p_build.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Skip confirmation prompts",
    )
    p_build.set_defaults(func=_dispatch_command)

    # --- run (parser only; handler in Stage 9) ---
    p_run = sub.add_parser("run", help="Launch a Pi container session")
    p_run.add_argument(
        "--project",
        action="append",
        default=[],
        dest="projects",
        metavar="PATH",
        help="Additional project to mount (repeatable)",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the run vector without executing",
    )
    p_run.set_defaults(func=_dispatch_command)

    # --- doctor (parser only; handler in Stage 9) ---
    p_doc = sub.add_parser(
        "doctor", help="Diagnose host → container connectivity",
    )
    p_doc.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Apply rootless override without prompting",
    )
    p_doc.set_defaults(func=_dispatch_command)

    # --- verify (parser only; handler in Stage 9) ---
    p_ver = sub.add_parser(
        "verify", help="Verify image and runtime integrity",
    )
    p_ver.add_argument(
        "--scope",
        choices=("build", "runtime", "all"),
        default="all",
        help="Which scopes to verify (default: all)",
    )
    p_ver.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output verification results as JSON",
    )
    p_ver.set_defaults(func=_dispatch_command)

    # --- show ---
    p_show = sub.add_parser(
        "show", help="Display reviewed inventory contents",
    )
    p_show.add_argument(
        "--scope",
        choices=("build", "runtime", "all"),
        default="all",
        help="Which sections to display (default: all)",
    )
    p_show.add_argument(
        "--effective",
        action="store_true",
        default=False,
        help="Display the effective projection instead of the"
             " reviewed source",
    )
    p_show.add_argument(
        "--override",
        action="append",
        default=[],
        dest="overrides",
        metavar="PATH=VALUE",
        help="Override a version value (repeatable, requires --effective)",
    )
    p_show.set_defaults(func=_dispatch_command)

    # --- check-updates ---
    p_upd = sub.add_parser(
        "check-updates", help="Check configured providers for updates",
    )
    p_upd.add_argument(
        "--scope",
        choices=("build", "runtime", "all"),
        default="all",
        help="Which scopes to check (default: all)",
    )
    p_upd.add_argument(
        "--only",
        action="append",
        default=[],
        dest="only_filter",
        metavar="FILTER",
        help="Provider name or inventory path (repeatable)",
    )
    p_upd.add_argument(
        "--include-prerelease",
        action="store_true",
        default=False,
        help="Include prerelease versions in queries",
    )
    p_upd.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat provider failures as errors",
    )
    p_upd.add_argument(
        "--fail-on-outdated",
        action="store_true",
        default=False,
        help="Exit non-zero when any applicable update is found",
    )
    p_upd.add_argument(
        "--suggest",
        action="store_true",
        default=False,
        help="Include non-mutating TOML suggestions in output",
    )
    p_upd.add_argument(
        "--cache-ttl",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Cache TTL in seconds",
    )
    p_upd.add_argument(
        "--cache-dir",
        default=None,
        metavar="PATH",
        help="Disk cache directory",
    )
    p_upd.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable HTTP cache",
    )
    p_upd.set_defaults(func=_dispatch_command)

    return parser


# ═══════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════

_IsAtty = Callable[[], bool]


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    dispatcher: Optional[CommandDispatcher | Callable[[str, CommandRequest], CommandResult]] = None,
    stdout_isatty: Optional[_IsAtty] = None,
    stderr_isatty: Optional[_IsAtty] = None,
) -> int:
    """Parse arguments, dispatch, render, and map to exit code.

    Parameters
    ----------
    argv:
        Argument list (defaults to ``sys.argv[1:]``).
    dispatcher:
        Domain boundary — a callable ``(command, request) -> CommandResult``
        or an object with an ``execute`` method. The default dispatcher
        delegates to the internal read-only service.
    stdout_isatty:
        Terminal-detection override for stdout (for colour logic).
        Defaults to ``sys.stdout.isatty``.
    stderr_isatty:
        Terminal-detection override for stderr (for colour logic).
        Defaults to ``sys.stderr.isatty``.
    """
    parser = _build_parser()
    disp = dispatcher or _real_dispatcher

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code is not None and exc.code != 0:
            return _EXIT_CODES[ExitKind.CLI]
        return _EXIT_CODES[ExitKind.SUCCESS]

    result: CommandResult
    try:
        result = args.func(args, dispatcher=disp)
    except FileNotFoundError as exc:
        result = CommandResult(
            exit_kind=ExitKind.CONFIG,
            message=f"inventory not found: {exc}",
        )
    except OSError as exc:
        result = CommandResult(
            exit_kind=ExitKind.CONFIG,
            message=f"cannot read inventory: {exc}",
        )
    except ValueError as exc:
        result = CommandResult(
            exit_kind=ExitKind.CONFIG,
            message=f"invalid configuration: {exc}",
        )
    except RuntimeError as exc:
        result = CommandResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=str(exc),
        )
    except NotImplementedError as exc:
        result = CommandResult(
            exit_kind=ExitKind.OPERATIONAL,
            message=str(exc),
        )

    _stdout_tty = (stdout_isatty() if stdout_isatty is not None
                   else getattr(sys.stdout, "isatty", lambda: False)())
    _stderr_tty = (stderr_isatty() if stderr_isatty is not None
                   else getattr(sys.stderr, "isatty", lambda: False)())

    stdout_text, stderr_text = _render(
        args.command,
        result,
        fmt=args.output,
        color=args.color,
        verbose=args.verbose,
        stdout_is_tty=_stdout_tty,
        stderr_is_tty=_stderr_tty,
    )

    if stdout_text:
        print(stdout_text, file=sys.stdout)
    if stderr_text:
        print(stderr_text, file=sys.stderr)

    return _EXIT_CODES[result.exit_kind]
