#!/bin/sh
# Verify the runtime contract after building an image.
set -eu
IMAGE="${1:-pi-cli-pi:latest}"

docker run --rm -e CHOWN_WORK_ON_START=0 "$IMAGE" bash -c '
  set -eu
  INVENTORY="/usr/local/share/pi-cli/versions.toml"
  HELPER="/usr/local/lib/pi-cli/docker/versions.py"

  test "$(id -un)" = dev

  for command in pi openspec node cargo rustc rustfmt uv ty rtk fd; do
    command -v "$command" >/dev/null || { echo "MISSING: $command" >&2; exit 1; }
    "$command" --version >/dev/null || { echo "FAILED: $command --version" >&2; exit 1; }
  done

  # --- Inventory availability checks ---
  test -f "$INVENTORY" || { echo "MISSING: $INVENTORY" >&2; exit 1; }
  inv_owner=$(stat -c "%U:%G" "$INVENTORY")
  test "$inv_owner" = "root:root" || { echo "OWNERSHIP MISMATCH: $INVENTORY expected root:root, got $inv_owner" >&2; exit 1; }
  inv_mode=$(stat -c "%a" "$INVENTORY")
  test "$inv_mode" = "444" || { echo "MODE MISMATCH: $INVENTORY expected 444, got $inv_mode" >&2; exit 1; }
  test -r "$INVENTORY" || { echo "ERROR: dev cannot read $INVENTORY" >&2; exit 1; }
  if test -w "$INVENTORY"; then echo "ERROR: dev can write $INVENTORY (should be 0444)" >&2; exit 1; fi
  echo "inventory ok"

  # --- Python checks ---
  python_path=$(command -v python3)
  test "$python_path" != /usr/local/bin/python3
  python_realpath=$(readlink -f "$python_path")
  case "$python_realpath" in
    */.local/share/uv/python/*/bin/python3*) ;;
    *) echo "python3 is not the uv-managed direct interpreter: $python_realpath" >&2; exit 1 ;;
  esac
  expected_python="$(python3 "$HELPER" get --inventory "$INVENTORY" stages.toolchain.python.version)"
  python3 -c "import sys; v=sys.version_info; actual=f\"{v.major}.{v.minor}.{v.micro}\"; assert actual == \"$expected_python\", actual"
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
  # Compare installed versions against inventory using normalized exact match.
  # Detects v-prefix skew (e.g. inventory has "vX.Y.Z" but binary reports "X.Y.Z")
  # and false matches from substring acceptance (e.g. "0.1.29" matching "0.1.299").
  _normalize_version() {
    # Strip an optional leading v/V, then emit as-is.
    case "$1" in
      v*|V*) printf "%s" "${1#?}" ;;
      *) printf "%s" "$1" ;;
    esac
  }
  _extract_version() {
    # Extract the first dotted numeric token from a multi-word version line.
    # Works for: "tool-name X.Y.Z (...)", "tool-name vX.Y.Z", etc.
    output="$1"
    printf "%s" "$output" | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | head -1
  }
  check_version() {
    tool="$1"
    path="$2"
    expected_raw="$(python3 "$HELPER" get --inventory "$INVENTORY" "$path")"
    expected="$( _normalize_version "$expected_raw" )"
    output="$("$tool" --version 2>&1)" || { echo "FAILED: $tool --version" >&2; exit 1; }
    actual="$( _extract_version "$output" )"
    if [ -z "$actual" ]; then
      echo "CANNOT PARSE VERSION from $tool output: $output" >&2
      exit 1
    fi
    if [ "$actual" != "$expected" ]; then
      echo "VERSION MISMATCH: $tool expected $expected (normalized from $expected_raw), got $actual" >&2
      echo "  full output: $output" >&2
      exit 1
    fi
  }
  check_version rustc stages.toolchain.rust.version
  check_version cargo stages.toolchain.rust.version
  # rustfmt and clippy have their own versioning (e.g. 1.8.0-stable, 0.1.88).
  # Component presence is verified earlier via "rustup component list".
  check_version uv stages.toolchain.uv.version
  check_version ty stages.toolchain.ty.version
  # Node image tags encode major+distro (e.g. "NN-trixie-slim"). Validate that
  # node --version reports the expected major (e.g. v24.X.Y).
  node_tag="$(python3 "$HELPER" get --inventory "$INVENTORY" stages.base.node.tag)"
  node_major="$(printf "%s" "$node_tag" | grep -oE '^[0-9]+')"
  node_actual="$(node --version | grep -oE '^v[0-9]+\.')"
  if [ "$node_actual" != "v${node_major}." ]; then
    echo "NODE MAJOR MISMATCH: expected v${node_major}.X, got $(node --version)" >&2
    exit 1
  fi
  check_version pi stages.pi-tools.pi.version
  check_version openspec stages.openspec-tools.openspec.version
  check_version rtk stages.rtk-prebuilt.rtk.version
  check_version fd stages.fd-prebuilt.fd.version
  echo "version checks ok"

  echo "=== pi extension setup script checks ==="
  script="/home/dev/install-pi-extensions.sh"
  test -f "$script" || { echo "MISSING: $script" >&2; exit 1; }
  script_owner=$(stat -c "%U:%G" "$script")
  test "$script_owner" = "root:root" || { echo "OWNERSHIP MISMATCH: $script expected root:root, got $script_owner" >&2; exit 1; }
  script_mode=$(stat -c "%a" "$script")
  test "$script_mode" = "755" || { echo "MODE MISMATCH: $script expected 755, got $script_mode" >&2; exit 1; }
  if ! test -r "$script"; then echo "ERROR: dev cannot read $script" >&2; exit 1; fi
  if ! test -x "$script"; then echo "ERROR: dev cannot execute $script" >&2; exit 1; fi
  if test -w "$script"; then echo "ERROR: dev can write $script (should be root:root 755)" >&2; exit 1; fi
  echo "pi extension setup script ok"

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
  printf "[project]\nname = '\''runtime-smoke'\''\nversion = '\''0.1.0'\''\n" > "$project/pyproject.toml"
  mkdir "$project/src"
  (cd "$project" && python3 -c "import os; assert not os.environ.get(\"VIRTUAL_ENV\")")
  (cd /tmp && python3 -c "import os; assert not os.environ.get(\"VIRTUAL_ENV\")")
  for _ in 1 2 3 4; do
    (cd "$project" && python3 -c "print(\"direct python\")") &
  done
  wait
  echo "ALL CHECKS PASSED"
'

echo "runtime tool and PATH checks passed for ${IMAGE}"
