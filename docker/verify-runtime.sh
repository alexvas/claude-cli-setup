#!/bin/sh
# Verify the runtime contract after building an image.
set -eu
IMAGE="${1:-pi-cli-pi:latest}"

docker run --rm "$IMAGE" bash -c '
  set -eu
  test "$(id -un)" = dev

  for command in pi openspec cargo uv ty rtk fd; do
    command -v "$command" >/dev/null || { echo "MISSING: $command" >&2; exit 1; }
    "$command" --version >/dev/null || { echo "FAILED: $command --version" >&2; exit 1; }
  done

  python_path=$(command -v python3)
  test "$python_path" != /usr/local/bin/python3
  python_realpath=$(readlink -f "$python_path")
  case "$python_realpath" in
    */.local/share/uv/python/*/bin/python3*) ;;
    *) echo "python3 is not the uv-managed direct interpreter: $python_realpath" >&2; exit 1 ;;
  esac
  python3 -c "import sys; assert sys.version_info >= (3, 14, 6), sys.version"
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
