#!/bin/sh
set -eu

PI_HOME="/home/dev/.pi"
INVENTORY="/usr/local/share/pi-cli/versions.toml"
HELPER="/usr/local/lib/pi-cli/docker/versions.py"

# Guard: refuse to write to image-layer .pi
if ! mountpoint -q -- "$PI_HOME"; then
  echo "ERROR: $PI_HOME is not a mount point." >&2
  echo "The Pi home must be mounted from the host before running this script." >&2
  echo "Example: python3 docker/versions.py compose run --rm pi /home/dev/install-pi-extensions.sh" >&2
  exit 1
fi

echo "=== Pi extension setup ==="

# Validate that pi, rtk, and the inventory helper are available
command -v pi >/dev/null 2>&1 || { echo "ERROR: pi not found on PATH" >&2; exit 1; }
command -v rtk >/dev/null 2>&1 || { echo "ERROR: rtk not found on PATH" >&2; exit 1; }

if [ ! -f "$INVENTORY" ]; then
  echo "ERROR: inventory not found at $INVENTORY" >&2
  exit 1
fi

# Read extensions from inventory and install each
# The helper emits JSON: {"pi-read": {"package": "..", "version": ".."}, ...}
extensions_json="$(python3 "$HELPER" extensions --inventory "$INVENTORY")"
echo "$extensions_json" | python3 -c "
import json, sys, subprocess, os

data = json.load(sys.stdin)
pi_home = os.environ.get('PI_HOME', os.path.expanduser('~/.pi'))

for name in sorted(data):
    entry = data[name]
    pkg = entry['package']
    version = entry['version']
    spec = f'npm:{pkg}@{version}'
    print(f'Installing {spec} ...')
    result = subprocess.run(['pi', 'install', spec], capture_output=True, text=True)
    if result.returncode != 0:
        print(f'ERROR installing {spec}:', file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    if result.stdout:
        sys.stdout.write(result.stdout)
    # Verify installed package metadata matches inventory.
    # Pi installs npm extensions under ~/.pi/agent/npm/node_modules/
    npm_root = os.path.join(pi_home, 'agent', 'npm', 'node_modules')
    pkg_json = os.path.join(npm_root, pkg.replace('/', os.sep), 'package.json')
    if not os.path.isfile(pkg_json):
        # Try unscoped fallback — some packages may install to a flat name
        flat_name = pkg.split('/')[-1] if '/' in pkg else pkg
        pkg_json = os.path.join(npm_root, flat_name, 'package.json')
    if not os.path.isfile(pkg_json):
        print(f'ERROR: cannot find package.json for {pkg} (tried {pkg_json})', file=sys.stderr)
        sys.exit(1)
    with open(pkg_json) as fh:
        installed = json.load(fh)
    installed_name = installed.get('name', '')
    installed_version = installed.get('version', '')
    if installed_name != pkg:
        print(f'ERROR: {pkg} package.json name mismatch: expected {pkg}, got {installed_name}', file=sys.stderr)
        sys.exit(1)
    if installed_version != version:
        print(f'ERROR: {pkg} version mismatch: expected {version}, got {installed_version}', file=sys.stderr)
        sys.exit(1)
    print(f'  verified: {pkg}@{installed_version}')
" || { echo "ERROR: extension installation failed" >&2; exit 1; }

# --- rtk integration (idempotent) ---

echo "Registering rtk integration ..."
rtk init -g --agent pi
rtk telemetry disable

echo "=== Pi extension setup complete ==="
