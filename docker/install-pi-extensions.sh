#!/bin/sh
set -eu

# Thin wrapper for the protected runtime extension installer.
# All configuration parsing, integrity verification, and package installation
# logic lives in the Python module at /usr/local/lib/pi-cli/docker/runtime_installer.py.
#
# This script is invoked by the entrypoint after ownership repair
# and before dropping privileges to dev.
#
# Manual invocation (recovery / testing):
#   /home/dev/install-pi-extensions.sh [--dry-run]

exec env PYTHONPATH=/usr/local/lib/pi-cli python3 -m docker.runtime_installer install "$@"
