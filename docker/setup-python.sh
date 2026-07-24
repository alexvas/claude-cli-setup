#!/usr/bin/env bash
set -euo pipefail

: "${PYTHON_VERSION:?PYTHON_VERSION must be set}"

if [[ ! ${PYTHON_VERSION} =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "PYTHON_VERSION must be a numeric release in X.Y.Z form (got ${PYTHON_VERSION})" >&2
  exit 1
fi

# Minimum-version and prerelease policy are validated by the resolver
# (stages.toolchain.python.override); this script enforces only that
# uv installs the exact requested version.

export PATH="${HOME}/.local/bin:${PATH}"
uv python install --default "${PYTHON_VERSION}"

python_bin="$(readlink -f "$(uv python find "${PYTHON_VERSION}")")"
case "${python_bin}" in
  "${HOME}/.local/share/uv/python/"*) ;;
  *)
    echo "uv python find returned a non-uv-managed executable: ${python_bin}" >&2
    exit 1
    ;;
esac

test -x "${python_bin}"
if [[ "$("${python_bin}" --version)" != "Python ${PYTHON_VERSION}" ]]; then
  echo "uv installed an unexpected Python executable: ${python_bin}" >&2
  "${python_bin}" --version >&2
  exit 1
fi

for command_name in python python3; do
  if ! command_path="$(command -v "${command_name}")"; then
    echo "Missing direct ${command_name} executable" >&2
    exit 1
  fi
  command_realpath="$(readlink -f "${command_path}")"
  if [[ "${command_realpath}" != "${python_bin}" ]]; then
    echo "${command_name} does not resolve to the uv-managed Python: ${command_realpath}" >&2
    exit 1
  fi
  if [[ "$("${command_path}" --version)" != "Python ${PYTHON_VERSION}" ]]; then
    echo "${command_name} has an unexpected version" >&2
    "${command_path}" --version >&2
    exit 1
  fi
done

"${python_bin}" --version
