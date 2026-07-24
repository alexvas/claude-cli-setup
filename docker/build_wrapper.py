#!/usr/bin/env python3
"""
Prepare Docker host reachability (rootless/rootful), probe via ephemeral host
HTTP server, then build the Pi image.

Version resolution is delegated to ``docker.versioning.rendering`` — the
wrapper does not maintain its own mapping of selected values.

Usage:
  python3 docker/build_wrapper.py diagnose
  python3 docker/build_wrapper.py apply [--yes]
  python3 docker/build_wrapper.py build [--yes] [--skip-override]
         [--inventory PATH] [--override PATH=VALUE] [--platform PLATFORM]
"""

from __future__ import annotations

import argparse
import http.server
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Lazy imports for version resolution — only loaded during build, not diagnose/apply
_versioning_imports: dict[str, object] = {}

ROOT = Path(__file__).resolve().parent.parent
DOCKER_DIR = Path(__file__).resolve().parent
PROBE_IMAGE = os.environ.get("BUILD_WRAPPER_PROBE_IMAGE", "alpine:3.20")
OVERRIDE_SRC = DOCKER_DIR / "rootless-docker.override.conf"
OVERRIDE_DEST = Path.home() / ".config/systemd/user/docker.service.d/override.conf"


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


class HostProbeServer:
    """Minimal HTTP server on 0.0.0.0:RAND_PORT returning a fixed probe token."""

    def __init__(self) -> None:
        self.token = f"OK_{int(time.time())}"
        self.port = 0
        self._httpd: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> int:
        token = self.token

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(token.encode())

            def log_message(self, format: str, *args: object) -> None:
                pass

        self._httpd = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


@dataclass
class ProbeResult:
    candidate: str
    ok: bool
    resolved_ip: str | None
    detail: str


@dataclass
class Diagnosis:
    rootless: bool
    probe_port: int
    probe_token: str
    lan_ip: str | None
    probes: list[ProbeResult] = field(default_factory=list)
    chosen_gateway: str | None = None
    override_installed: bool = False
    override_needed: bool = False

    @property
    def host_gateway_ip(self) -> str | None:
        """Concrete IP for .env / Dockerfile (privoxy, extra_hosts)."""
        if self.chosen_gateway is None:
            return None
        for p in self.probes:
            if p.candidate == self.chosen_gateway and p.ok:
                return p.resolved_ip or p.candidate
        return None

    def chosen_probe(self) -> ProbeResult | None:
        if self.chosen_gateway is None:
            return None
        for p in self.probes:
            if p.candidate == self.chosen_gateway and p.ok:
                return p
        return None


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


def detect_lan_ip() -> str | None:
    try:
        out = run(["hostname", "-I"], check=True).stdout.strip()
        if out:
            return out.split()[0]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    try:
        out = run(["ip", "-4", "route", "show", "default"], check=False).stdout
        m = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)\b", out)
        if m:
            return m.group(1)
    except FileNotFoundError:
        pass
    return None


def docker_rootless() -> bool:
    try:
        out = run(["docker", "info"], check=True).stdout.lower()
        return "rootless" in out
    except subprocess.CalledProcessError as e:
        print(e.stderr or e.stdout, file=sys.stderr)
        raise


def override_matches() -> bool:
    if not OVERRIDE_DEST.is_file():
        return False
    try:
        return OVERRIDE_DEST.read_text(encoding="utf-8") == OVERRIDE_SRC.read_text(encoding="utf-8")
    except OSError:
        return False


def candidates(rootless: bool, lan_ip: str | None) -> list[str]:
    if rootless:
        order = ["10.0.2.2"]
        if lan_ip:
            order.append(lan_ip)
        order.append("host-gateway")
        return order
    order = ["host-gateway"]
    if lan_ip:
        order.append(lan_ip)
    return order


def probe_host_mapping(candidate: str, probe_port: int, expected_token: str) -> ProbeResult:
    add_host = f"host.docker.internal:{candidate}"
    # shell: fetch body and compare to expected token
    script = (
        "getent hosts host.docker.internal | awk '{print $1}' | head -1 | "
        "while read ip; do echo RESOLVED_IP=$ip; done; "
        f"body=$(wget -qO- --timeout=3 http://host.docker.internal:{probe_port} 2>/dev/null) && "
        f'echo "$body" | grep -qx "{expected_token}" && echo PROBE_OK'
    )
    cmd = [
        "docker",
        "run",
        "--rm",
        "--add-host",
        add_host,
        PROBE_IMAGE,
        "sh",
        "-c",
        script,
    ]
    try:
        proc = run(cmd, check=False)
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = "PROBE_OK" in out
        resolved = None
        m = re.search(r"RESOLVED_IP=(\S+)", out)
        if m:
            resolved = m.group(1)
        detail = out.strip()[-200:] if out.strip() else f"exit {proc.returncode}"
        return ProbeResult(candidate, ok, resolved, detail)
    except subprocess.CalledProcessError as e:
        return ProbeResult(candidate, False, None, (e.stderr or str(e))[:200])


def choose_gateway(diagnosis: Diagnosis) -> str | None:
    for probe in diagnosis.probes:
        if probe.ok:
            return probe.candidate
    return None


def print_diagnosis(d: Diagnosis) -> None:
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


def apply_rootless_override(*, assume_yes: bool) -> None:
    if not OVERRIDE_SRC.is_file():
        raise SystemExit(f"Missing {OVERRIDE_SRC}")
    print(f"Will install {OVERRIDE_SRC} -> {OVERRIDE_DEST}")
    print("Will run: systemctl --user daemon-reload && systemctl --user restart docker.service")
    if not confirm("Apply rootless port-forward override?", assume_yes=assume_yes):
        print("Skipped override apply.")
        return
    OVERRIDE_DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OVERRIDE_SRC, OVERRIDE_DEST)
    run(["systemctl", "--user", "daemon-reload"], check=True)
    run(["systemctl", "--user", "restart", "docker.service"], check=True)
    print("Waiting for Docker daemon...")
    time.sleep(3)
    print("Rootless override applied.")


def update_env_file(path: Path, updates: dict[str, str], *, remove_keys: Iterable[str] = ()) -> None:
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    remove = set(remove_keys)
    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.strip().startswith("#") else ""
        if key in remove:
            continue
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    removed = ", ".join(remove_keys) if remove_keys else ""
    print(f"Updated {path}: {', '.join(updates.keys())}" + (f"; removed {removed}" if removed else ""))


def run_diagnosis(
    env: dict[str, str],
    *,
    probe_after_override: bool = True,
) -> Diagnosis:
    rootless = docker_rootless()
    lan_ip = detect_lan_ip()
    server = HostProbeServer()
    try:
        probe_port = server.start()
        d = Diagnosis(
            rootless=rootless,
            probe_port=probe_port,
            probe_token=server.token,
            lan_ip=lan_ip,
            override_installed=override_matches(),
            override_needed=rootless and not override_matches(),
        )
        for cand in candidates(rootless, lan_ip):
            d.probes.append(probe_host_mapping(cand, probe_port, server.token))
        d.chosen_gateway = choose_gateway(d)
        if d.chosen_gateway is None and rootless and d.override_needed and probe_after_override:
            print("No candidate worked; rootless override may be required (run apply).")
        return d
    finally:
        server.stop()


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


def cmd_diagnose(args: argparse.Namespace) -> int:
    dotenv = load_dotenv(ROOT / ".env")
    d = run_diagnosis(merge_env(dotenv))
    print_diagnosis(d)
    return 0 if d.host_gateway_ip else 1


def cmd_apply(args: argparse.Namespace) -> int:
    if not docker_rootless():
        print("Not rootless Docker; override not needed.")
        return 0
    apply_rootless_override(assume_yes=args.yes)
    dotenv = load_dotenv(ROOT / ".env")
    d = run_diagnosis(merge_env(dotenv))
    print_diagnosis(d)
    return 0 if d.host_gateway_ip else 1


def cmd_build(args: argparse.Namespace) -> int:
    env_path = ROOT / ".env"
    dotenv = load_dotenv(env_path)
    merged = merge_env(dotenv)

    # Resolve version environment from docker-constructor.toml (not .env).
    # This is the single authoritative source — no duplicate mapping.
    # Reuse the canonical override parser so that duplicate paths,
    # whitespace, and empty tokens are rejected consistently.
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
        # Inventory validation, override policy, effective config
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except tomllib.TOMLDecodeError as exc:
        print(f"error: invalid TOML in inventory: {exc}", file=sys.stderr)
        return 3
    except EffectiveInventoryOutputError as exc:
        # Unsafe --effective-inventory-output path
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: inventory not found: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"error: cannot read inventory: {exc}", file=sys.stderr)
        return 3

    if docker_rootless() and not override_matches() and not args.skip_override:
        print("Rootless Docker without port-forward override.")
        if args.yes:
            apply_rootless_override(assume_yes=True)
        elif confirm("Apply rootless override now before probe?", assume_yes=False):
            apply_rootless_override(assume_yes=True)
        else:
            print("Continuing without override (probe may fail).")

    d = run_diagnosis(merged)
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
    args.yes = effective_yes(args)
    if args.command == "diagnose":
        return cmd_diagnose(args)
    if args.command == "apply":
        return cmd_apply(args)
    if args.command == "build":
        return cmd_build(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
