"""CLI argument parsing, exit-code mapping, and output.

No Docker, no network, no subprocess (except for the compose command).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Optional, Sequence

from .effective import (
    EffectiveConfiguration,
    apply_overrides,
    effective_environment,
    get_path,
    serialize_effective_inventory,
    to_plain_data,
)
from .errors import (
    InventoryError,
    OverrideValidationError,
    UnknownPathError,
    UnsupportedOverrideError,
    VersionConfigError,
)
import tomllib
from .inventory import load_inventory, validate_inventory

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_UNKNOWN_PATH = 4
EXIT_UNSUPPORTED_OVERRIDE = 5
EXIT_OVERRIDE_POLICY = 6


def _parse_overrides(raw: Sequence[str]) -> dict[str, str]:
    """Parse ``PATH=VALUE`` override tokens.

    Rejects tokens with leading/trailing spaces, duplicate paths,
    or other malformations.
    """
    result: dict[str, str] = {}
    for token in raw:
        if "=" not in token:
            raise ValueError(f"invalid override {token!r}: expected PATH=VALUE")
        path, value = token.split("=", 1)
        if path != path.strip() or value != value.strip():
            raise ValueError(
                f"invalid override {token!r}: no spaces allowed around '='"
            )
        if not path:
            raise ValueError(f"invalid override {token!r}: empty path")
        if path in result:
            raise ValueError(
                f"duplicate override path {path!r}: each path may only be "
                f"specified once"
            )
        result[path] = value
    return result


def _cmd_validate(
    args: argparse.Namespace,
    effective: EffectiveConfiguration,
) -> int:
    if args.json:
        print(json.dumps({"valid": True}, sort_keys=True))
    else:
        print("valid")
    return EXIT_OK


def _cmd_get(
    args: argparse.Namespace,
    effective: EffectiveConfiguration,
) -> int:
    try:
        value = get_path(effective, args.path)
    except UnknownPathError:
        raise

    if args.json:
        print(_json_dumps(value))
    elif isinstance(value, (str, int, float, bool, type(None))):
        print(str(value))
    else:
        print(_json_dumps(value))
    return EXIT_OK


def _shell_escape(value: str) -> str:
    """Return *value* safe for shell eval / source.

    Wraps in single quotes, escaping embedded single quotes as ``'\\''``.

    >>> _shell_escape("hello")
    "'hello'"
    >>> _shell_escape("it's")
    "'it'\\''s'"
    """
    return "'" + value.replace("'", "'\\''") + "'"


def _cmd_env(
    args: argparse.Namespace,
    effective: EffectiveConfiguration,
) -> int:
    env = effective_environment(effective)
    if args.json:
        print(_json_dumps(to_plain_data(env)))
    else:
        for name in sorted(env):
            print(f"export {name}={_shell_escape(env[name])}")
    return EXIT_OK


def _json_dumps(value: object) -> str:
    from types import MappingProxyType

    def _convert(v: object) -> object:
        if isinstance(v, (str, int, float, bool, type(None))):
            return v
        if isinstance(v, MappingProxyType):
            return dict(v)
        if isinstance(v, (tuple, list)):
            return [_convert(x) for x in v]
        if hasattr(v, "items"):
            return {str(k): _convert(val) for k, val in v.items()}  # type: ignore[union-attr]
        return str(v)

    return json.dumps(
        _convert(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="versions",
        description="Manage Docker toolchain versions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Common options shared by all subcommands
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--inventory",
        default=None,
        metavar="PATH",
        help="Path to versions.toml (default: versions.toml in repo root)",
    )
    common.add_argument(
        "--override",
        action="append",
        default=[],
        dest="overrides",
        metavar="PATH=VALUE",
        help="Override a version value (repeatable)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output in JSON format",
    )

    # validate
    sub.add_parser("validate", parents=[common], help="Validate versions.toml")

    # get
    get_p = sub.add_parser(
        "get", parents=[common], help="Get a configuration value"
    )
    get_p.add_argument(
        "path",
        help="Dot-separated path (e.g. stages.toolchain.python.version)",
    )

    # env
    sub.add_parser(
        "env", parents=[common], help="Emit effective environment variables"
    )

    return parser


def _resolve_default_inventory() -> Path:
    """Find versions.toml in the repo root (parent of docker/)."""
    return Path(__file__).parent.parent.parent / "versions.toml"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve inventory path
    if args.inventory:
        inventory_path = Path(args.inventory)
    else:
        inventory_path = _resolve_default_inventory()

    # Load inventory
    try:
        inventory = load_inventory(inventory_path)
    except VersionConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except FileNotFoundError as exc:
        print(f"error: inventory not found: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except tomllib.TOMLDecodeError as exc:
        print(f"error: malformed TOML: {exc}", file=sys.stderr)
        return EXIT_INVALID
    except OSError as exc:
        print(f"error: cannot read inventory: {exc}", file=sys.stderr)
        return EXIT_INVALID

    # Parse overrides
    try:
        overrides_raw = _parse_overrides(args.overrides)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    # Validate / apply overrides
    try:
        effective = apply_overrides(inventory, overrides_raw)
    except UnsupportedOverrideError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNSUPPORTED_OVERRIDE
    except OverrideValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_OVERRIDE_POLICY

    # Dispatch command
    try:
        if args.command == "validate":
            return _cmd_validate(args, effective)
        elif args.command == "get":
            return _cmd_get(args, effective)
        elif args.command == "env":
            return _cmd_env(args, effective)
    except UnknownPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN_PATH
    except VersionConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID

    return EXIT_OK
