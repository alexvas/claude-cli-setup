#!/usr/bin/env python3
"""
Prepare Docker host reachability (rootless/rootful), probe via ephemeral host
HTTP server, then build the Pi image.

Version resolution is delegated to ``docker.versioning.rendering`` — the
wrapper does not maintain its own mapping of selected values.

Domain logic (detection, probing, override planning/application,
gateway persistence) is delegated to ``docker.networking``.  This
module retains only CLI argument parsing, user prompts, presentation,
exit-code policy, and build orchestration.

Usage:
  python3 docker/build_wrapper.py diagnose
  python3 docker/build_wrapper.py apply [--yes]
  python3 docker/build_wrapper.py build [--yes] [--skip-override]
         [--inventory PATH] [--override PATH=VALUE] [--platform PLATFORM]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from docker.networking import (
    DockerDetectionError,
    DockerMode,
    GatewayDiagnosis,
    apply_rootless_override,
    detect_docker_mode,
    diagnose_gateway,
    plan_rootless_override,
    update_env_file,
)

# Lazy imports for version resolution — only loaded during build, not diagnose/apply
_versioning_imports: dict[str, object] = {}

ROOT = Path(__file__).resolve().parent.parent
PROBE_IMAGE = os.environ.get("BUILD_WRAPPER_PROBE_IMAGE", "alpine:3.20")


def resolve_build_inputs(
    inventory_path: Path | None = None,
    overrides: dict[str, str] | None = None,
    *,
    platform: str = "linux-amd64",
    inventory_output: str = ".docker-generated/docker-constructor.toml",
) -> dict[str, str]:
    """Resolve version build arguments from ``docker-constructor.toml``.

    Delegates to ``docker.versioning.rendering`` so that
    ``build_wrapper.py`` and ``versions.py compose`` produce identical
    build environments.
    """
    from docker.versioning.inventory import load_inventory
    from docker.versioning.effective import apply_overrides
    from docker.versioning.rendering import (
        render_build_environment,
        write_effective_inventory,
    )

    if inventory_path is None:
        inventory_path = ROOT / "docker-constructor.toml"
    inv = load_inventory(inventory_path)
    eff = apply_overrides(inv, overrides or {})

    # Write the effective inventory so that the Docker build input
    # (EFFECTIVE_VERSIONS_FILE) actually exists.
    write_effective_inventory(
        eff,
        ROOT / inventory_output,
        repo_root=ROOT,
        output_path=inventory_output,
    )

    return dict(render_build_environment(
        eff,
        platform=platform,
        inventory_output=inventory_output,
    ))


def run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        text=True,
        capture_output=True,
        check=check,
    )


def load_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Compose expands ${VAR} values from .env, so mirror that behavior
        # before forwarding parsed values through subprocess.env.
        env[key.strip()] = os.path.expandvars(value.strip())
    return env


def merge_env(base: dict[str, str]) -> dict[str, str]:
    merged = dict(base)
    for key, value in os.environ.items():
        if key.startswith("_"):
            continue
        merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Presentation (the only UI concern this module still owns)
# ---------------------------------------------------------------------------


def print_diagnosis(d: GatewayDiagnosis) -> None:
    print(f"Docker mode: {'rootless' if d.rootless else 'rootful'}")
    print(f"Probe image: {PROBE_IMAGE}")
    print(f"Host probe: 0.0.0.0:{d.probe_port} token={d.probe_token}")
    print(f"LAN IP: {d.lan_ip or '(not detected)'}")
    print(f"Rootless override installed: {d.override_installed}")
    if d.rootless and not d.override_installed:
        print("Rootless override recommended: docker/build_wrapper.py apply")
    print("\nProbe results (host.docker.internal -> candidate):")
    for p in d.probes:
        status = "OK" if p.ok else "FAIL"
        resolved = p.resolved_ip or "-"
        print(f"  {p.candidate:16}  {status:4}  resolved={resolved}  ({p.detail[:60]})")
    if d.host_gateway_ip:
        chosen = d.chosen_probe()
        if chosen and not chosen.resolved_ip:
            print(
                f"\nChosen HOST_GATEWAY_IP: {d.host_gateway_ip} "
                f"(fallback: probe OK, resolved IP unavailable)"
            )
        else:
            print(f"\nChosen HOST_GATEWAY_IP: {d.host_gateway_ip}")
    else:
        print("\nNo working host gateway candidate found.")


def confirm(prompt: str, *, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


def _detect_mode_or_exit() -> DockerMode:
    """Run mode detection; print to stderr and exit on failure."""
    try:
        return detect_docker_mode()
    except DockerDetectionError as exc:
        print(f"Error: cannot detect Docker mode — {exc}", file=sys.stderr)
        raise SystemExit(1)


def _diagnose_and_print() -> GatewayDiagnosis:
    d = diagnose_gateway(probe_image=PROBE_IMAGE)
    print_diagnosis(d)
    return d


def compose_build(env_extra: dict[str, str], services: Iterable[str]) -> None:
    env = os.environ.copy()
    env.update(env_extra)
    for svc in services:
        print(f"\n=== docker compose build {svc} ===")
        proc = subprocess.run(
            ["docker", "compose", "build", svc],
            cwd=ROOT,
            env=env,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)


# ---------------------------------------------------------------------------
# CLI commands (argparse entry points)
# ---------------------------------------------------------------------------


def cmd_diagnose(args: argparse.Namespace) -> int:
    d = _diagnose_and_print()
    return 0 if d.host_gateway_ip else 1


def cmd_apply(args: argparse.Namespace) -> int:
    mode = _detect_mode_or_exit()
    if mode is not DockerMode.ROOTLESS:
        print("Not rootless Docker; override not needed.")
        return 0
    plan = plan_rootless_override(_mode=mode)
    if not plan.needed:
        print("Rootless override already matches — nothing to apply.")
        return 0
    if not plan.src.is_file():
        print(f"Missing override source file: {plan.src}", file=sys.stderr)
        return 1

    print(f"Will install {plan.src} -> {plan.dest}")
    print("Will run: systemctl --user daemon-reload && systemctl --user restart docker.service")
    if not confirm("Apply rootless port-forward override?", assume_yes=args.yes):
        print("Skipped override apply.")
        return 0

    failure = apply_rootless_override(plan, consent=True)
    if failure is not None:
        print(f"Override failed: {failure.operation}: {failure.detail}",
              file=sys.stderr)
        return 1
    print("Rootless override applied.")

    d = _diagnose_and_print()
    return 0 if d.host_gateway_ip else 1


def cmd_build(args: argparse.Namespace) -> int:
    env_path = ROOT / ".env"
    dotenv = load_dotenv(env_path)
    merged = merge_env(dotenv)

    # Resolve version environment from docker-constructor.toml (not .env).
    # This is the single authoritative source — no duplicate mapping.
    inventory_path = getattr(args, "inventory", None)
    if inventory_path:
        inventory_path = Path(inventory_path)
    overrides_raw: list[str] = getattr(args, "overrides", []) or []
    platform = getattr(args, "platform", "linux-amd64")

    from docker.versioning.cli import _parse_overrides
    import tomllib
    from docker.versioning.errors import VersionConfigError
    from docker.versioning.rendering import EffectiveInventoryOutputError

    try:
        overrides = _parse_overrides(overrides_raw)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        version_env = resolve_build_inputs(
            inventory_path=inventory_path,
            overrides=overrides or None,
            platform=platform,
        )
    except VersionConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except tomllib.TOMLDecodeError as exc:
        print(f"error: invalid TOML in inventory: {exc}", file=sys.stderr)
        return 3
    except EffectiveInventoryOutputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: inventory not found: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"error: cannot read inventory: {exc}", file=sys.stderr)
        return 3

    # --- Override check (delegated to docker.networking) ---
    try:
        mode = detect_docker_mode()
    except DockerDetectionError as exc:
        print(f"Error: cannot detect Docker mode — {exc}", file=sys.stderr)
        return 1

    if mode is DockerMode.ROOTLESS and not args.skip_override:
        plan = plan_rootless_override(_mode=mode)
        if plan.needed:
            print("Rootless Docker without port-forward override.")
            if args.yes or confirm(
                "Apply rootless override now before probe?", assume_yes=False
            ):
                print(f"Will install {plan.src} -> {plan.dest}")
                print("Will run: systemctl --user daemon-reload &&"
                      " systemctl --user restart docker.service")
                failure = apply_rootless_override(plan, consent=True)
                if failure is not None:
                    print(f"Override failed: {failure.operation}:"
                          f" {failure.detail}", file=sys.stderr)
                    return 1
            else:
                print("Continuing without override (probe may fail).")

    d = diagnose_gateway(probe_image=PROBE_IMAGE)
    print_diagnosis(d)
    if not d.host_gateway_ip:
        print("\nCannot build: no route to host from container.", file=sys.stderr)
        print("Try: python3 docker/build_wrapper.py apply", file=sys.stderr)
        return 1

    updates = {"HOST_GATEWAY_IP": d.host_gateway_ip}
    print(f"\nWill set in .env: {updates}")
    if not confirm("Write .env and run docker compose build?", assume_yes=args.yes):
        print("Aborted.")
        return 0

    if not env_path.is_file():
        example = ROOT / ".env.example"
        if example.is_file():
            shutil.copy2(example, env_path)
            print(f"Created {env_path} from .env.example")
    update_env_file(env_path, updates, remove_keys=["SOCKS_HOST"])
    print(f"Updated {env_path}: HOST_GATEWAY_IP")

    # Combine: operational values from .env (merged) first,
    # then validated version values override only conflicting
    # version keys, then diagnostic updates (HOST_GATEWAY_IP) last.
    env_extra = {**merged, **version_env, **updates}
    compose_build(env_extra, ["pi"])
    print("\nPi build finished.")
    return 0


def add_yes_arg(parser: argparse.ArgumentParser, *, dest: str = "yes") -> None:
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        dest=dest,
        help="Skip confirmation prompts",
    )


def effective_yes(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "yes", False) or getattr(args, "yes_global", False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_yes_arg(parser, dest="yes_global")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("diagnose", help="Probe host reachability only")

    p_apply = sub.add_parser("apply", help="Install rootless override and re-probe")
    add_yes_arg(p_apply)

    p_build = sub.add_parser("build", help="Probe, update .env, build images")
    add_yes_arg(p_build)
    p_build.add_argument("--skip-override", action="store_true", help="Do not offer rootless override")
    p_build.add_argument(
        "--inventory",
        default=None,
        metavar="PATH",
        help="Path to docker-constructor.toml (default: docker-constructor.toml in repo root)",
    )
    p_build.add_argument(
        "--override",
        action="append",
        default=[],
        dest="overrides",
        metavar="PATH=VALUE",
        help="Override a version value (repeatable)",
    )
    p_build.add_argument(
        "--platform",
        default="linux-amd64",
        metavar="PLATFORM",
        help="Target platform (default: linux-amd64)",
    )

    args = parser.parse_args()
    yes_value = effective_yes(args)

    match args.command:
        case "diagnose":
            return cmd_diagnose(args)
        case "apply":
            return cmd_apply(args)
        case "build":
            return cmd_build(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
