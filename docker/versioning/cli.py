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
    get_path,
    serialize_effective_inventory,
    to_plain_data,
)
from .rendering import (
    compose_command,
    render_build_environment,
)
from .errors import (
    InventoryError,
    OverrideValidationError,
    UnknownFilterError,
    UnknownPathError,
    UnsupportedOverrideError,
    UpdateError,
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
EXIT_PROVIDER_FAILURE = 7
EXIT_OUTDATED = 8


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
    """Write effective inventory and emit full build environment.

    Mirrors the Compose contract: the generated effective inventory is
    written to disk and ``EFFECTIVE_VERSIONS_FILE`` is included in the
    output so that ``eval "$(./docker/versions.py env)" && docker
    compose …`` works identically to ``versions.py compose``.
    """
    from pathlib import Path
    from .rendering import (
        EffectiveInventoryOutputError,
        write_effective_inventory,
    )

    inventory_output = getattr(
        args, "effective_inventory_output",
        ".docker-generated/versions.toml",
    )
    platform = getattr(args, "platform", "linux-amd64")
    repo_root = Path(__file__).parent.parent.parent
    try:
        write_effective_inventory(
            effective,
            repo_root / inventory_output,
            repo_root=repo_root,
            output_path=inventory_output,
        )
    except EffectiveInventoryOutputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    env = render_build_environment(effective, platform=platform, inventory_output=inventory_output)
    if args.json:
        print(_json_dumps(to_plain_data(env)))
    else:
        for name in sorted(env):
            print(f"export {name}={_shell_escape(env[name])}")
    return EXIT_OK


def _cmd_compose(
    args: argparse.Namespace,
    effective: EffectiveConfiguration,
) -> int:
    """Write effective inventory, render build environment, run compose."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    from .rendering import (
        compose_command,
        EffectiveInventoryOutputError,
        write_effective_inventory,
    )

    platform = getattr(args, "platform", "linux-amd64")
    inventory_output = getattr(
        args, "effective_inventory_output",
        ".docker-generated/versions.toml",
    )

    # Strip leading '--' if argparse.REMAINDER preserved it
    compose_args: list[str] = list(getattr(args, "compose_args", []) or [])
    if compose_args and compose_args[0] == "--":
        compose_args = compose_args[1:]

    # 1. Write generated effective inventory
    repo_root = Path(__file__).parent.parent.parent
    try:
        write_effective_inventory(
            effective,
            repo_root / inventory_output,
            repo_root=repo_root,
            output_path=inventory_output,
        )
    except EffectiveInventoryOutputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    # 2. Render build environment
    env_vars = render_build_environment(
        effective,
        platform=platform,
        inventory_output=inventory_output,
    )

    # 3. Merge with os.environ (resolved values take priority)
    process_env = os.environ.copy()
    process_env.update(env_vars)

    # 3a. Runtime compose file for non-build operations.
    #     docker compose build must not evaluate runtime interpolation;
    #     run / config / exec / up need the runtime project requirements.
    #     Skip global Compose options to find the actual subcommand.
    _RUNTIME_FILE = "docker-compose.runtime.yml"
    _BASE_FILE = "docker-compose.yml"
    _runtime_ops = {"run", "config", "exec", "up"}
    _global_flags = frozenset({
        "--compatibility", "--dry-run", "--no-ansi", "--no-parallel",
        "--quiet-pull", "--verbose",
    })
    _global_value_opts = frozenset({
        "--ansi", "--env-file", "--file", "-f", "--parallel",
        "--progress", "--profile", "--project-directory",
        "--project-name", "-p",
    })
    _first_op = ""
    _has_explicit_file = False
    i = 0
    while i < len(compose_args):
        a = compose_args[i]
        if a in _global_value_opts:
            if a in ("-f", "--file"):
                _has_explicit_file = True
            i += 2  # skip --opt value
        elif a in _global_flags:
            i += 1
        elif "=" in a and a.split("=", 1)[0] in _global_value_opts:
            opt_name = a.split("=", 1)[0]
            if opt_name in ("-f", "--file"):
                _has_explicit_file = True
            i += 1  # --opt=value single token
        elif "=" in a and a.split("=", 1)[0] in _global_flags:
            i += 1
        elif a.startswith("-"):
            i += 1  # unknown option — assume safe to skip
        else:
            _first_op = a
            break
    if _first_op in _runtime_ops and "COMPOSE_FILE" not in process_env:
        if _has_explicit_file:
            # -f overrides COMPOSE_FILE — inject as leading -f pair so
            # Compose evaluates them before the user's explicit files.
            compose_args = (
                ["-f", _BASE_FILE, "-f", _RUNTIME_FILE] + compose_args
            )
        else:
            process_env["COMPOSE_FILE"] = f"{_BASE_FILE}:{_RUNTIME_FILE}"

    # 4. Run docker compose
    cmd = compose_command(compose_args)
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(repo_root),
            env=process_env,
            check=False,
        )
        return proc.returncode
    except FileNotFoundError:
        print(
            f"error: docker not found — is Docker installed and on PATH?",
            file=sys.stderr,
        )
        return 1


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
    env_p = sub.add_parser(
        "env", parents=[common], help="Emit effective environment variables"
    )
    env_p.add_argument(
        "--platform",
        default="linux-amd64",
        metavar="PLATFORM",
        help="Target platform for artifact selection (default: linux-amd64)",
    )
    env_p.add_argument(
        "--effective-inventory-output",
        default=".docker-generated/versions.toml",
        metavar="PATH",
        help="Path for generated effective inventory (default: .docker-generated/versions.toml)",
    )

    # compose
    compose_p = sub.add_parser(
        "compose",
        parents=[common],
        help="Render build args and run docker compose",
    )
    compose_p.add_argument(
        "--platform",
        default="linux-amd64",
        metavar="PLATFORM",
        help="Target platform for artifact selection (default: linux-amd64)",
    )
    compose_p.add_argument(
        "--effective-inventory-output",
        default=".docker-generated/versions.toml",
        metavar="PATH",
        help="Path for generated effective inventory (default: .docker-generated/versions.toml)",
    )
    compose_p.add_argument(
        "compose_args",
        nargs=argparse.REMAINDER,
        help="Arguments for docker compose (after --)",
    )

    # check-updates (separate common args — overrides are not relevant here)
    updates_common = argparse.ArgumentParser(add_help=False)
    updates_common.add_argument(
        "--inventory",
        default=None,
        metavar="PATH",
        help="Path to versions.toml (default: versions.toml in repo root)",
    )
    updates_common.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output in JSON format",
    )

    updates_p = sub.add_parser(
        "check-updates",
        parents=[updates_common],
        help="Check configured providers for updates",
    )
    updates_p.add_argument(
        "--only",
        action="append",
        default=[],
        dest="only",
        metavar="FILTER",
        help="Provider name or inventory path (repeatable)",
    )
    updates_p.add_argument(
        "--include-prerelease",
        action="store_true",
        default=False,
        dest="include_prerelease",
        help="Include prerelease versions in provider queries",
    )
    updates_p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat provider failures as errors (exit 7)",
    )
    updates_p.add_argument(
        "--fail-on-outdated",
        action="store_true",
        default=False,
        dest="fail_on_outdated",
        help="Exit with code 8 when any applicable update is found",
    )
    updates_p.add_argument(
        "--suggest",
        action="store_true",
        default=False,
        help="Include non-mutating TOML suggestions in output",
    )
    updates_p.add_argument(
        "--cache-ttl",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Cache TTL in seconds (persists to disk across invocations)",
    )
    updates_p.add_argument(
        "--cache-dir",
        default=None,
        metavar="PATH",
        dest="cache_dir",
        help="Disk cache directory (default: $XDG_CACHE_HOME/pi-cli/versioning)",
    )
    updates_p.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        dest="no_cache",
        help="Disable HTTP cache",
    )

    # extensions — emit Pi extension metadata as JSON for runtime scripts
    ext_p = sub.add_parser(
        "extensions",
        help="Emit Pi extension metadata as JSON",
    )
    ext_p.add_argument(
        "--inventory",
        default=None,
        metavar="PATH",
        dest="inventory_path",
        help="Path to versions.toml (default: versions.toml in repo root)",
    )

    return parser


def _cmd_extensions(args: argparse.Namespace) -> int:
    """Emit Pi extension metadata as JSON for runtime scripts."""
    import json as _json
    from pathlib import Path as _Path
    from .inventory import load_inventory

    if args.inventory_path:
        inv_path = _Path(args.inventory_path)
    else:
        inv_path = _Path(__file__).parent.parent.parent / "versions.toml"
    inv = load_inventory(inv_path)
    result: dict[str, dict[str, str]] = {}
    for name, entry in sorted(inv.runtime_pi_extensions.items()):
        result[name] = {
            "package": entry.source.package,
            "version": entry.version,
        }
    print(_json.dumps(result, indent=2))
    return EXIT_OK


def _resolve_transports(args: argparse.Namespace):
    """Build production HTTP / git transports for *args*."""
    from .providers.base import HttpTransport, GitRefTransport

    class _ProductionHttp(HttpTransport):
        def request(self, method, url, *, headers=(), nocache=False):
            import urllib.request
            import urllib.error
            req = urllib.request.Request(url, method=method, headers=dict(headers))
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read()
                    return type("HttpResponse", (), {
                        "status": resp.status,
                        "headers": dict(resp.headers),
                        "body": body,
                    })()
            except urllib.error.HTTPError as e:
                body = e.read() if hasattr(e, "read") else b""
                return type("HttpResponse", (), {
                    "status": e.code,
                    "headers": dict(e.headers) if hasattr(e, "headers") else {},
                    "body": body,
                })()
            except OSError as e:
                # SocketTimeout, ConnectionError, etc. — treat as
                # provider unavailable rather than crashing the CLI.
                return type("HttpResponse", (), {
                    "status": 503,
                    "headers": {},
                    "body": f"timeout_or_connection_error: {e}".encode(),
                })()

    class _ProductionGit(GitRefTransport):
        def resolve_ref(self, repository, ref):
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "ls-remote", repository, ref],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip())
                line = result.stdout.strip().split("\n")[0]
                return line.split()[0]
            except FileNotFoundError:
                raise RuntimeError("git executable not found")

    from .cache import CachingHttpTransport, DiskCache, _default_cache_dir
    from .model import CacheConfig
    http = _ProductionHttp()
    no_cache: bool = getattr(args, "no_cache", False)
    if not no_cache:
        cache_ttl: int | None = getattr(args, "cache_ttl", None)
        cache_dir: str | None = getattr(args, "cache_dir", None)

        # Read [cache] section from validated inventory
        inv_cache: CacheConfig | None = getattr(args, "_inventory_cache", None)
        if inv_cache is not None:
            if cache_dir is None and inv_cache.dir is not None:
                cache_dir = inv_cache.dir
            if cache_ttl is None and inv_cache.ttl is not None:
                cache_ttl = inv_cache.ttl

        # In --suggest mode, never create or write to a disk cache.
        # The guarantee is that --suggest mutates nothing on the
        # filesystem, including the cache directory — even when
        # [cache].dir or --cache-dir points inside the working tree.
        suggest_mode: bool = getattr(args, "suggest", False)
        if not suggest_mode:
            if cache_dir is not None:
                disk = DiskCache(Path(cache_dir), ttl=cache_ttl)
            else:
                disk = DiskCache(_default_cache_dir(), ttl=cache_ttl) if cache_ttl is not None else None
            http = CachingHttpTransport(http, ttl=cache_ttl, disk_cache=disk)
        else:
            disk = None
            # In-memory only — reads from cache directory would
            # themselves be non-mutating, but for simplicity and to
            # avoid any edge case we omit the disk tier entirely.
            http = CachingHttpTransport(http, ttl=cache_ttl, disk_cache=disk)
    return http, _ProductionGit()


def _resolve_tokens() -> dict[str, str]:
    """Collect provider tokens from environment variables."""
    import os as _os
    tokens: dict[str, str] = {}
    for var in ("GITHUB_TOKEN", "NPM_TOKEN", "PYPI_TOKEN", "DOCKER_REGISTRY_TOKEN"):
        val = _os.environ.get(var)
        if val:
            tokens[var] = val
    return tokens


def _cmd_check_updates(
    args: argparse.Namespace,
    inventory: object,
) -> int:
    """Run check-updates with provider results."""
    from .updates import (
        _DEFAULT_PROVIDERS,
        check_updates,
        render_table,
        render_json,
        render_suggestions,
        render_suggestions_json,
    )
    from .providers.base import ProviderContext
    from .model import CacheConfig

    # Pass validated cache config from inventory to transport layer
    args._inventory_cache = getattr(inventory, "cache", None)

    http, git = _resolve_transports(args)
    tokens = _resolve_tokens()

    context = ProviderContext(
        http=http,
        git=git,
        include_prerelease=args.include_prerelease,
        tokens=tokens,
    )

    only = tuple(args.only) if hasattr(args, "only") else ()

    results = check_updates(
        inventory,
        context=context,
        only=only,
    )

    # Output
    if args.json:
        if args.suggest:
            output = render_suggestions_json(results)
        else:
            output = render_json(results)
        print(output)
    else:
        table = render_table(results)
        print(table)
        if args.suggest:
            print()
            print("# Suggested updates:")
            print(render_suggestions(results) or "(none)")

    # Exit code logic
    strict = getattr(args, "strict", False)
    fail_on_outdated = getattr(args, "fail_on_outdated", False)

    if strict and any(r.status.value == "unavailable" for r in results):
        return EXIT_PROVIDER_FAILURE
    if fail_on_outdated and any(
        r.status.value == "outdated" and r.applicable for r in results
    ):
        return EXIT_OUTDATED

    return EXIT_OK


def _resolve_default_inventory() -> Path:
    """Find versions.toml in the repo root (parent of docker/)."""
    return Path(__file__).parent.parent.parent / "versions.toml"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # check-updates and extensions use their own inventory path —
    # they don't need the common `--inventory` arg
    if args.command == "check-updates":
        # check-updates needs inventory loaded for cache config
        inv_path = Path(args.inventory) if getattr(args, "inventory", None) else _resolve_default_inventory()
        try:
            inventory = load_inventory(inv_path)
        except (VersionConfigError, FileNotFoundError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_INVALID
        try:
            return _cmd_check_updates(args, inventory)
        except UnknownFilterError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        except VersionConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_INVALID

    if args.command == "extensions":
        try:
            return _cmd_extensions(args)
        except FileNotFoundError as exc:
            print(f"error: inventory not found: {exc}", file=sys.stderr)
            return EXIT_INVALID
        except tomllib.TOMLDecodeError as exc:
            print(f"error: malformed TOML: {exc}", file=sys.stderr)
            return EXIT_INVALID
        except VersionConfigError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_INVALID
        except OSError as exc:
            print(f"error: cannot read inventory: {exc}", file=sys.stderr)
            return EXIT_INVALID

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

    # Parse overrides (for validate, get, env, compose commands)
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
        elif args.command == "compose":
            return _cmd_compose(args, effective)
    except UnknownPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN_PATH
    except VersionConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID

    return EXIT_OK
