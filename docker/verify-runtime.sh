#!/bin/sh
# Smoke-test a built Pi runtime image for basic contract compliance.
#
# This script validates structural invariants (tool presence, user
# identity, ownership, mount detection) by generating an effective
# runtime projection and mounting it read-only into a temporary
# container.
#
# For version-level and extension-integrity verification use the
# constructor facade:
#
#     # Build-scope checks (tool versions inside image):
#     ./docker/docker-constructor.py verify --scope build --image "$IMAGE"
#
#     # Runtime-scope checks (extensions, ownership, mounts):
#     ./docker/docker-constructor.py verify --scope runtime \
#         --image "$IMAGE"                          \
#         --container <container-name>               \
#         --runtime-projection <host-path.toml>
#
#     # Both scopes (auto-detects container):
#     ./docker/docker-constructor.py verify --image "$IMAGE"
#
set -eu
IMAGE="${1:-pi-cli-pi:latest}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Generate a minimal effective runtime projection ──────────────
PROJ_FILE=$(mktemp /tmp/pi-runtime-smoke-proj.XXXXXX.toml)
PI_HOME_DIR=$(mktemp -d /tmp/pi-runtime-smoke-home.XXXXXX)
trap 'rm -rf "$PROJ_FILE" "$PI_HOME_DIR"' EXIT

PYTHONPATH="$REPO_DIR" python3 -c '
import sys, shutil
from pathlib import Path
from docker.versioning.inventory import load_inventory
from docker.versioning.effective import resolve_runtime, create_runtime_projection

inv = load_inventory(Path(sys.argv[2]) / "docker-constructor.toml")
proj = resolve_runtime(inv.runtime, {})
with create_runtime_projection(proj) as h:
    shutil.copy2(h.path, sys.argv[1])
' "$PROJ_FILE" "$REPO_DIR"

# ── Run smoke checks inside a temporary container ────────────────
docker run --rm \
    -e CHOWN_WORK_ON_START=0 \
    --mount "type=bind,src=$PROJ_FILE,dst=/run/pi-cli/docker-constructor.runtime.toml,readonly" \
    --mount "type=bind,src=$PI_HOME_DIR,dst=/home/dev/.pi" \
    "$IMAGE" bash -c '
  set -eu

  test "$(id -un)" = dev

  # Runtime projection — mounted read-only by the constructor launcher.
  RUNTIME_PROJ="/run/pi-cli/docker-constructor.runtime.toml"
  test -f "$RUNTIME_PROJ" || { echo "MISSING: $RUNTIME_PROJ" >&2; exit 1; }
  test -r "$RUNTIME_PROJ" || { echo "ERROR: dev cannot read $RUNTIME_PROJ" >&2; exit 1; }
  if test -w "$RUNTIME_PROJ"; then echo "ERROR: dev can write $RUNTIME_PROJ (should be ro mount)" >&2; exit 1; fi
  echo "runtime projection ok"

  for command in pi openspec node cargo rustc rustfmt uv ty rtk fd; do
    command -v "$command" >/dev/null || { echo "MISSING: $command" >&2; exit 1; }
    "$command" --version >/dev/null || { echo "FAILED: $command --version" >&2; exit 1; }
  done

  echo "=== Python checks ==="
  python_path=$(command -v python3)
  test "$python_path" != /usr/local/bin/python3
  python_realpath=$(readlink -f "$python_path")
  case "$python_realpath" in
    */.local/share/uv/python/*/bin/python3*) ;;
    *) echo "python3 is not the uv-managed direct interpreter: $python_realpath" >&2; exit 1 ;;
  esac
  python3 -c "import sys; v=sys.version_info; print(f\"{v.major}.{v.minor}.{v.micro}\")" >/dev/null || {
    echo "FAILED: python3 version introspection" >&2; exit 1
  }
  test "$(readlink -f "$(command -v python)")" = "$python_realpath"
  if command -v pip >/dev/null 2>&1; then
    echo "UNEXPECTED: pip command is available" >&2
    exit 1
  fi
  if command -v pip3 >/dev/null 2>&1; then
    echo "UNEXPECTED: pip3 command is available" >&2
    exit 1
  fi
  for shell_config in /etc/profile /etc/profile.d/*.sh "$HOME/.profile" "$HOME/.bash_profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
    test -f "$shell_config" || continue
    if grep -Eq "alias (python|python3|pip|pip3)=" "$shell_config"; then
      echo "UNEXPECTED Python/pip alias in active shell config: $shell_config" >&2
      exit 1
    fi
  done

  echo "=== rust component checks ==="
  for component in clippy rustfmt; do
    rustup component list 2>/dev/null | grep -q "$component.*(installed)" || {
      echo "MISSING Rust component: $component" >&2
      exit 1
    }
  done
  cargo clippy --version >/dev/null || { echo "FAILED: cargo clippy --version" >&2; exit 1; }
  echo "rust components ok"

  echo "=== version checks ==="
  # Validate that every installed tool reports a parseable dotted version.
  # Exact version matches are verified host-side by docker-constructor.py verify.
  _extract_version() {
    output="$1"
    printf "%s" "$output" | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1
  }
  for tool in rustc cargo uv ty pi openspec rtk fd; do
    output="$("$tool" --version 2>&1)" || { echo "FAILED: $tool --version" >&2; exit 1; }
    actual="$( _extract_version "$output" )"
    if [ -z "$actual" ]; then
      echo "CANNOT PARSE VERSION from $tool output: $output" >&2
      exit 1
    fi
    echo "  $tool $actual ok"
  done
  # Node image tags encode major+distro (e.g. "NN-trixie-slim"). Verify
  # that node --version reports a recognizable Node version.
  node --version | grep -qE "^v[0-9]+\." || { echo "FAILED: node --version" >&2; exit 1; }
  echo "version checks ok"

  echo "=== pi extension setup checks ==="
  # Legacy wrapper must be absent after remove-install-pi-extensions-wrapper.
  test ! -f /home/dev/install-pi-extensions.sh || { echo "STALE: /home/dev/install-pi-extensions.sh must be absent" >&2; exit 1; }
  # Protected Python installer module must be present at the known path.
  installer="/usr/local/lib/pi-cli/docker/runtime_installer.py"
  test -f "$installer" || { echo "MISSING: $installer" >&2; exit 1; }
  test -r "$installer" || { echo "UNREADABLE: $installer" >&2; exit 1; }
  # Entrypoint must invoke the protected Python installer, not a shell wrapper.
  entrypoint="/usr/local/bin/docker-entrypoint.sh"
  test -x "$entrypoint" || { echo "NOT EXECUTABLE: $entrypoint" >&2; exit 1; }
  grep -qF "docker.runtime_installer install" "$entrypoint" || { echo "ENTRYPOINT MISSING installer invocation" >&2; exit 1; }
  echo "pi extension setup ok"

  echo "=== automatic extension installation outcomes ==="
  # After entrypoint runs the installer, extensions must be present under Pi home.
  agent_dir="/home/dev/.pi/agent"
  test -d "$agent_dir" || { echo "MISSING: $agent_dir" >&2; exit 1; }
  # At least one installed extension must have a readable package.json.
  found=0
  for pkg_json in "$agent_dir"/npm/node_modules/*/package.json \
                  "$agent_dir"/npm/node_modules/@*/*/package.json; do
    test -f "$pkg_json" || continue
    test -r "$pkg_json" || continue
    pkg_name=$(python3 -c "import json; print(json.load(open('$pkg_json')).get('name',''))" 2>/dev/null || true)
    pkg_version=$(python3 -c "import json; print(json.load(open('$pkg_json')).get('version',''))" 2>/dev/null || true)
    test -n "$pkg_name" || continue
    test -n "$pkg_version" || continue
    echo "  installed: $pkg_name@$pkg_version"
    found=$((found + 1))
  done
  test "$found" -gt 0 || { echo "FAILED: no installed extensions found under $agent_dir/npm/node_modules" >&2; exit 1; }
  # Installed extension files must be owned by dev:dev.
  mismatch=$(find "$agent_dir/npm/node_modules" -maxdepth 4 \( ! -user dev -o ! -group dev \) -print -quit 2>/dev/null || true)
  test -z "$mismatch" || { echo "OWNERSHIP MISMATCH in installed extensions: $mismatch" >&2; exit 1; }
  echo "automatic extension installation ok"

  echo "=== rtk integration outcomes ==="
  # rtk init -g --agent pi creates an extension under the Pi home.
  test -f "$agent_dir/extensions/rtk.ts" || { echo "MISSING rtk extension at $agent_dir/extensions/rtk.ts" >&2; exit 1; }
  # rtk telemetry disable must have been applied.
  enabled_line=$(rtk telemetry status 2>&1 | grep 'enabled:' || true)
  case "$enabled_line" in
    *"enabled: no"*|"enabled: false"*) ;;
    *) echo "rtk telemetry not disabled: $enabled_line" >&2; exit 1 ;;
  esac
  echo "rtk integration ok"

  echo "=== ownership checks ==="
  required_paths="/home/dev/.local /home/dev/.rustup /home/dev/.cargo/bin /home/dev/mcp /home/dev/work /home/dev/.npm-global"
  for path in $required_paths; do
    test -e "$path" || { echo "MISSING image-provided path: $path" >&2; exit 1; }
  done
  find_err=$(mktemp)
  set +e
  mismatch=$(find $required_paths \( ! -user dev -o ! -group dev \) -print -quit 2>"$find_err")
  find_rc=$?
  set -e
  if [ "$find_rc" -ne 0 ]; then
    echo "OWNERSHIP TRAVERSAL FAILED (exit $find_rc):" >&2
    cat "$find_err" >&2
    rm -f "$find_err"
    exit 1
  fi
  rm -f "$find_err"
  if [ -n "$mismatch" ]; then
    actual=$(stat -c "%U:%G (uid=%u gid=%g mode=%a)" -- "$mismatch")
    echo "OWNERSHIP MISMATCH: $mismatch" >&2
    echo "  expected: dev:dev" >&2
    echo "  actual:   $actual" >&2
    exit 1
  fi
  echo "ownership ok"

  echo "=== mount checks ==="
  command -v mountpoint >/dev/null 2>&1 || { echo "MISSING mountpoint command" >&2; exit 1; }
  mountpoint -q -- / || { echo "FAILED: mountpoint detection not working" >&2; exit 1; }
  echo "mount detection ok"

  project=$(mktemp -d)
  trap "rm -rf \"$project\"" EXIT
  printf "[project]\nname = \"runtime-smoke\"\nversion = \"0.1.0\"\n" > "$project/pyproject.toml"
  mkdir "$project/src"
  (cd "$project" && python3 -c "import os; assert not os.environ.get(\"VIRTUAL_ENV\")")
  (cd /tmp && python3 -c "import os; assert not os.environ.get(\"VIRTUAL_ENV\")")
  for _ in 1 2 3 4; do
    (cd "$project" && python3 -c "print(\"direct python\")") &
  done
  wait
  echo "ALL CHECKS PASSED"
'

echo "runtime smoke checks passed for ${IMAGE}"
