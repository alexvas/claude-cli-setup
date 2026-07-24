#!/usr/bin/env python3
"""Host-side acceptance verifier for versioned Docker images.

Loads a host-side effective inventory, runs the image, reads the in-image
inventory, and asserts:

- Effective inventory ownership (root:root 0444) and runtime-helper parity
- Installed-version equality across the full tool matrix
- Direct Python contract (no pip, uv-managed CPython path)
- Pi extension pins when ``--pi-home`` is provided
- Artifact digest mismatch detection
- Non-zero exit with path-qualified diagnostics on mismatch

Usage::

    python3 docker/verify_versioned_image.py \\
        --image pi-cli-pi:latest \\
        --inventory .docker-generated/versions.toml

Optional::

    --pi-home PATH            Mount Pi home (as /home/dev/.pi) and verify extensions
    --skip-extensions         Skip extension verification (faster smoke test)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify a versioned Docker image")
    p.add_argument("--image", required=True, help="Docker image tag to verify")
    p.add_argument(
        "--inventory", required=True,
        help="Path to host-side effective inventory TOML (e.g. .docker-generated/versions.toml)",
    )
    p.add_argument(
        "--pi-home", default=None,
        help="Mount Pi home directory and verify extensions",
    )
    p.add_argument(
        "--skip-extensions", action="store_true",
        help="Skip extension verification even when --pi-home is provided",
    )
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _docker_run(image: str, *args: str, mounts: dict[str, str] | None = None,
                env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a command inside the image and return the CompletedProcess.

    Always sets CHOWN_WORK_ON_START=0 so the entrypoint does not attempt
    ownership repair against read-only mounts.
    """
    cmd = ["docker", "run", "--rm"]
    for host, container in (mounts or {}).items():
        cmd += ["-v", f"{host}:{container}:ro"]
    merged_env = {"CHOWN_WORK_ON_START": "0"}
    merged_env.update(env or {})
    for k, v in merged_env.items():
        cmd += ["-e", f"{k}={v}"]
    cmd.append(image)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _inventory_get(inventory: dict, *path: str) -> str:
    """Walk nested dict by dotted path, return string value."""
    d = inventory
    for key in path:
        if not isinstance(d, dict):
            _fail(f"inventory path {'.'.join(path)}: expected dict at {key!r}")
        if key not in d:
            _fail(f"inventory path {'.'.join(path)}: missing key {key!r}")
        d = d[key]
    return str(d)


def _normalize_version(v: str) -> str:
    """Strip optional leading v/V for exact comparison."""
    if v.startswith("v") or v.startswith("V"):
        return v[1:]
    return v


# ---------------------------------------------------------------------------
# Executable Python snippet for image-inventory read
# ---------------------------------------------------------------------------

_IMAGE_INV_SNIPPET = (
    "import json,tomllib;"
    "f=open('/usr/local/share/pi-cli/versions.toml','rb');"
    "d=tomllib.load(f);"
    "f.close();"
    "print(json.dumps(d,sort_keys=True))"
)

def _image_inv_snippet() -> str:
    """Return the Python snippet used to read the image inventory.

    Separated so tests can compile() and eval() it without Docker.
    """
    return _IMAGE_INV_SNIPPET


# ---------------------------------------------------------------------------
# Inventory comparison
# ---------------------------------------------------------------------------

def _load_inventory(path: str) -> dict:
    """Load a TOML inventory file, returning a plain dict."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as f:
        return tomllib.load(f)


def _read_image_inventory(image: str) -> dict:
    """Read the effective inventory from inside the image as JSON."""
    proc = _docker_run(image, "python3", "-c", _image_inv_snippet())
    if proc.returncode != 0:
        _fail(f"failed to read image inventory (exit {proc.returncode}):\n{proc.stderr}")
    return json.loads(proc.stdout)


def _compare_inventories(host: dict, image: dict) -> int:
    """Deep-compare complete host and image inventories.

    Traverses every key recursively and reports every leaf-level
    difference.  Returns the number of mismatched paths.
    """
    mismatches = 0

    def _walk(h: dict | list, i: dict | list, path: str) -> None:
        nonlocal mismatches
        if isinstance(h, dict) and isinstance(i, dict):
            all_keys = h.keys() | i.keys()
            for k in sorted(all_keys):
                child_path = f"{path}.{k}" if path else k
                if k not in h:
                    print(f"MISMATCH {child_path}: missing in host, image has {i[k]!r}")
                    mismatches += 1
                elif k not in i:
                    print(f"MISMATCH {child_path}: host has {h[k]!r}, missing in image")
                    mismatches += 1
                else:
                    _walk(h[k], i[k], child_path)
        elif isinstance(h, list) and isinstance(i, list):
            if len(h) != len(i):
                print(f"MISMATCH {path}: host list len {len(h)}, image list len {len(i)}")
                mismatches += 1
                return
            for idx, (hv, iv) in enumerate(zip(h, i)):
                _walk(hv, iv, f"{path}[{idx}]")
        else:
            if h != i:
                print(f"MISMATCH {path}: host={h!r} image={i!r}")
                mismatches += 1

    _walk(host, image, "")
    return mismatches


# ---------------------------------------------------------------------------
# Ownership / mode checks
# ---------------------------------------------------------------------------

def _check_inventory_ownership(image: str) -> int:
    """Verify inventory file ownership and mode inside the image."""
    mismatches = 0
    proc = _docker_run(
        image, "stat", "-c", "%U:%G %a",
        "/usr/local/share/pi-cli/versions.toml",
    )
    if proc.returncode != 0:
        _fail(f"failed to stat image inventory (exit {proc.returncode}):\n{proc.stderr}")
    owner_mode = proc.stdout.strip()
    expected = "root:root 444"
    if owner_mode != expected:
        print(
            f"MISMATCH /usr/local/share/pi-cli/versions.toml ownership: "
            f"expected {expected!r} got {owner_mode!r}"
        )
        mismatches += 1

    # dev cannot write
    proc = _docker_run(
        image, "bash", "-c",
        "test -w /usr/local/share/pi-cli/versions.toml && echo WRITABLE || echo OK",
    )
    if "WRITABLE" in proc.stdout:
        print("FAIL: dev can write /usr/local/share/pi-cli/versions.toml")
        mismatches += 1

    # Runtime helper is root-owned and not dev-writable
    for path in ("/usr/local/lib/pi-cli/docker/versions.py",):
        proc = _docker_run(image, "stat", "-c", "%U:%G", path)
        if proc.returncode != 0:
            print(f"MISSING runtime helper: {path}")
            mismatches += 1
        elif proc.stdout.strip() != "root:root":
            print(f"MISMATCH {path} owner: expected root:root got {proc.stdout.strip()}")
            mismatches += 1
        proc = _docker_run(image, "bash", "-c", f"test -w {path} && echo WRITABLE || echo OK")
        if "WRITABLE" in proc.stdout:
            print(f"FAIL: dev can write {path}")
            mismatches += 1

    return mismatches


# ---------------------------------------------------------------------------
# Tool matrix verification
# ---------------------------------------------------------------------------

_TOOL_MATRIX = [
    ("rustc", "stages.toolchain.rust.version"),
    ("cargo", "stages.toolchain.rust.version"),
    ("uv", "stages.toolchain.uv.version"),
    ("ty", "stages.toolchain.ty.version"),
    ("pi", "stages.pi-tools.pi.version"),
    ("openspec", "stages.openspec-tools.openspec.version"),
    ("rtk", "stages.rtk-prebuilt.rtk.version"),
    ("fd", "stages.fd-prebuilt.fd.version"),
]


def _check_tool_versions(image: str, inventory: dict) -> int:
    """Run each tool inside the image and compare its version to inventory."""
    import re
    mismatches = 0
    version_re = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")

    for command, inv_path in _TOOL_MATRIX:
        proc = _docker_run(image, command, "--version")
        if proc.returncode != 0:
            print(f"FAILED: {command} --version (exit {proc.returncode}): {proc.stderr}")
            mismatches += 1
            continue

        output = proc.stdout + proc.stderr
        expected_raw = _inventory_get(inventory, *inv_path.split("."))
        match = version_re.search(output)
        if not match:
            print(f"CANNOT PARSE VERSION from {command} output: {output.strip()!r}")
            mismatches += 1
            continue
        actual = match.group(0)
        expected = _normalize_version(expected_raw)

        if actual != expected:
            print(
                f"VERSION MISMATCH {command}: "
                f"expected {expected} (from {expected_raw}), got {actual}"
            )
            print(f"  full output: {output.strip()}")
            mismatches += 1

    # Node: major-only comparison from image tag
    node_tag = _inventory_get(inventory, "stages", "base", "node", "tag")
    node_major = node_tag.split("-")[0]
    proc = _docker_run(image, "node", "--version")
    if proc.returncode != 0:
        print(f"FAILED: node --version (exit {proc.returncode}): {proc.stderr}")
        mismatches += 1
    else:
        node_m = re.match(r"v(\d+)\.", proc.stdout.strip())
        if not node_m or node_m.group(1) != node_major:
            print(
                f"NODE MAJOR MISMATCH: expected v{node_major}.X, "
                f"got {proc.stdout.strip()}"
            )
            mismatches += 1

    # Rust components: verify rustfmt and clippy are installed if listed
    try:
        components_raw = inventory["stages"]["toolchain"]["rust"]["components"]
    except (KeyError, TypeError):
        components_raw = []
    if isinstance(components_raw, list):
        proc = _docker_run(image, "rustup", "component", "list", "--installed")
        installed_lines = proc.stdout.splitlines() if proc.returncode == 0 else []
        for comp in components_raw:
            if not isinstance(comp, str):
                continue
            # --installed only lists installed components, so a <comp>- prefix
            # match is sufficient (no (installed) marker in --installed output).
            if not any(line.startswith(f"{comp}-") for line in installed_lines):
                print(f"FAILED: rust component {comp!r} is not installed")
                mismatches += 1
                continue
            # Verify the component is actually callable
            if comp == "rustfmt":
                pr = _docker_run(image, "rustfmt", "--version")
                if pr.returncode != 0:
                    print(
                        f"FAILED: rustfmt --version (exit {pr.returncode}): "
                        f"{pr.stderr.strip()}"
                    )
                    mismatches += 1
            elif comp == "clippy":
                pr = _docker_run(image, "cargo", "clippy", "--version")
                if pr.returncode != 0:
                    print(
                        f"FAILED: cargo clippy --version (exit {pr.returncode}): "
                        f"{pr.stderr.strip()}"
                    )
                    mismatches += 1

    return mismatches


# ---------------------------------------------------------------------------
# Direct Python contract
# ---------------------------------------------------------------------------

def _check_python_contract(image: str, inventory: dict) -> int:
    """Verify the direct Python contract inside the image."""
    mismatches = 0
    expected = _inventory_get(inventory, "stages", "toolchain", "python", "version")

    # Resolve actual python3 binary path
    proc = _docker_run(image, "bash", "-c", "command -v python3")
    if proc.returncode != 0:
        print(f"FAIL: python3 not found (exit {proc.returncode})")
        mismatches += 1
        py3_bin = None
    else:
        py3_bin = proc.stdout.strip()

    proc = _docker_run(image, "bash", "-c", "command -v python")
    if proc.returncode != 0:
        print(f"FAIL: python not found (exit {proc.returncode})")
        mismatches += 1
        py_bin = None
    else:
        py_bin = proc.stdout.strip()

    # Resolve real paths
    py3_real = ""
    py_real = ""
    if py3_bin:
        pr = _docker_run(image, "readlink", "-f", py3_bin)
        if pr.returncode != 0 or not pr.stdout.strip():
            print(
                f"FAIL: cannot resolve python3 ({py3_bin}) via readlink -f "
                f"(exit {pr.returncode}): {pr.stderr.strip()}"
            )
            mismatches += 1
        py3_real = pr.stdout.strip()
    if py_bin:
        pr = _docker_run(image, "readlink", "-f", py_bin)
        if pr.returncode != 0 or not pr.stdout.strip():
            print(
                f"FAIL: cannot resolve python ({py_bin}) via readlink -f "
                f"(exit {pr.returncode}): {pr.stderr.strip()}"
            )
            mismatches += 1
        py_real = pr.stdout.strip()

    # python and python3 must resolve to the same real path
    if py3_real and py_real and py3_real != py_real:
        print(
            f"FAIL: python and python3 point to different binaries: "
            f"python={py_real} python3={py3_real}"
        )
        mismatches += 1

    # Path must be inside /home/dev/.local/share/uv/python/
    if py3_real and ".local/share/uv/python/" not in py3_real:
        print(f"FAIL: python3 path not inside uv python dir: {py3_real}")
        mismatches += 1

    # Version exactly matches expected
    proc = _docker_run(image, "python3", "-c",
                       "import sys; v=sys.version_info; "
                       "print(f'{v.major}.{v.minor}.{v.micro}')")
    actual_ver = proc.stdout.strip()
    if actual_ver != expected:
        print(
            f"PYTHON VERSION MISMATCH: "
            f"expected {expected}, got {actual_ver}"
        )
        mismatches += 1

    # pip/pip3 must be absent
    for name in ("pip", "pip3"):
        proc = _docker_run(image, "bash", "-c", f"command -v {name}")
        if proc.returncode == 0:
            print(f"FAIL: {name} should not be present, found at: {proc.stdout.strip()}")
            mismatches += 1

    return mismatches


# ---------------------------------------------------------------------------
# Extension verification
# ---------------------------------------------------------------------------

# Snippet that reads package.json for a given npm package directory
# and prints {"name":...,"version":...}.
_READ_PACKAGE_JSON = (
    "import json,sys;"
    "p=json.load(open(sys.argv[1]+'/package.json'));"
    "print(json.dumps({'name':p.get('name',''),'version':p.get('version','')}))"
)


def _check_extensions(image: str, pi_home: str, inventory: dict) -> int:
    """Mount Pi home at /home/dev/.pi and verify every configured extension.

    For each extension in ``runtime.pi-extensions.<name>``:
    - Read ``source.package`` (the npm package identity).
    - Inspect ``$PI_HOME/agent/npm/node_modules/<package>/package.json``.
    - Assert ``name`` matches the npm package name and ``version`` matches
      the inventory version.
    """
    mismatches = 0

    try:
        pi_exts = inventory["runtime"]["pi-extensions"]
    except (KeyError, TypeError):
        return mismatches

    if not isinstance(pi_exts, dict):
        return mismatches

    # Collect expected extensions with name, version, npm package
    expected: list[tuple[str, str, str]] = []
    for name, info in pi_exts.items():
        if not isinstance(info, dict):
            continue
        ver = info.get("version")
        source = info.get("source", {})
        pkg = source.get("package") if isinstance(source, dict) else None
        if ver is not None and pkg is not None:
            expected.append((name, str(ver), str(pkg)))

    if not expected:
        return mismatches

    npm_root = "/home/dev/.pi/agent/npm/node_modules"

    for ext_name, inv_ver, npm_pkg in sorted(expected):
        pkg_dir = f"{npm_root}/{npm_pkg}"
        proc = _docker_run(
            image, "python3", "-c", _READ_PACKAGE_JSON, pkg_dir,
            mounts={pi_home: "/home/dev/.pi"},
        )
        if proc.returncode != 0:
            print(
                f"FAIL: extension {ext_name!r}: cannot read {pkg_dir}/package.json "
                f"(exit {proc.returncode}): {proc.stderr}"
            )
            mismatches += 1
            continue

        try:
            pkg_data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            print(f"FAIL: extension {ext_name!r}: invalid JSON from {pkg_dir}/package.json")
            mismatches += 1
            continue

        pkg_name = str(pkg_data.get("name", ""))
        pkg_ver = str(pkg_data.get("version", ""))

        # Version match
        norm_actual = _normalize_version(pkg_ver)
        norm_expected = _normalize_version(inv_ver)
        if norm_actual != norm_expected:
            print(
                f"EXTENSION VERSION MISMATCH {ext_name}: "
                f"expected {norm_expected} (from {inv_ver}), "
                f"got {norm_actual} (from {pkg_ver})"
            )
            mismatches += 1

        # Package name should match npm identity
        if pkg_name and pkg_name != npm_pkg:
            print(
                f"EXTENSION PACKAGE MISMATCH {ext_name}: "
                f"expected npm package {npm_pkg!r}, "
                f"got {pkg_name!r}"
            )
            mismatches += 1

    return mismatches


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])

    inventory_path = args.inventory
    if not os.path.isfile(inventory_path):
        _fail(f"inventory file not found: {inventory_path}")

    host_inv = _load_inventory(inventory_path)
    image_inv = _read_image_inventory(args.image)

    total_mismatches = 0

    print("=== inventory comparison ===")
    total_mismatches += _compare_inventories(host_inv, image_inv)
    if total_mismatches == 0:
        print("host ↔ image inventory: OK")

    print("\n=== ownership / mode ===")
    total_mismatches += _check_inventory_ownership(args.image)

    print("\n=== tool matrix ===")
    total_mismatches += _check_tool_versions(args.image, host_inv)

    print("\n=== Python contract ===")
    total_mismatches += _check_python_contract(args.image, host_inv)

    if args.pi_home and not args.skip_extensions:
        print("\n=== extensions ===")
        total_mismatches += _check_extensions(args.image, args.pi_home, host_inv)

    if total_mismatches > 0:
        print(f"\n{total_mismatches} mismatch(es) found", file=sys.stderr)
        return 1
    else:
        print("\nALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
