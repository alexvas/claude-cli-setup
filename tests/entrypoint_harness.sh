#!/bin/bash
# Entrypoint test harness — exercises the **real** docker/entrypoint.sh
# with fake boundaries.  Each invocation runs ONE scenario identified
# by the _SCENARIO environment variable.
#
# The harness:
#   1. Creates PATH-based stubs for all external commands
#   2. Shadows bash builtins (exec, command) with logging functions
#   3. Copies a scenario-specific projection file (if any) into the
#      fixed /run/pi-cli path the real entrypoint reads
#   4. Sources the real entrypoint.sh — its top-level guard executes
#   5. Dumps a parseable trace to stdout
#
# Every external command invocation, every exec attempt, and every
# exit/return is traced.  The real entrypoint's stdout/stderr are
# discarded — the test asserts ordering, not diagnostic wording.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENTRYPOINT_REAL="$SCRIPT_DIR/docker/entrypoint.sh"

SCENARIO="${_SCENARIO:-UNKNOWN}"

# ═══════════════════════════════════════════════════════════════════════
# Trace file (scenario tag is prepended by PATH stubs)
# ═══════════════════════════════════════════════════════════════════════
TRACE_FILE="$(mktemp)"
export TRACE_FILE SCENARIO
trap 'rm -f "$TRACE_FILE" 2>/dev/null || true' EXIT

_trace_line() {
  echo "${SCENARIO}: $*" >>"$TRACE_FILE"
}

# ═══════════════════════════════════════════════════════════════════════
# PATH-based stubs (invoked via gosu, env, or directly)
# ═══════════════════════════════════════════════════════════════════════
_FAKE_BIN="$(mktemp -d)"
trap 'rm -rf "$_FAKE_BIN" "$TRACE_FILE" "$_PROJ_FIXED" 2>/dev/null || true' EXIT
export PATH="$_FAKE_BIN:$PATH"

# -- id --
cat >"$_FAKE_BIN/id" <<'IDEOF'
#!/bin/bash
echo "${SCENARIO}: id $*" >>"${TRACE_FILE}"
if [ "${_ID_MODE:-root}" = "dev" ]; then
  if [ "${1:-}" = "-u" ]; then echo "1000"; else echo "uid=1000(dev) gid=1000(dev) groups=1000(dev)"; fi
else
  if [ "${1:-}" = "-u" ]; then echo "0"; else echo "uid=0(root) gid=0(root) groups=0(root)"; fi
fi
exit 0
IDEOF
chmod +x "$_FAKE_BIN/id"

# -- mountpoint --
cat >"$_FAKE_BIN/mountpoint" <<'MPEOF'
#!/bin/bash
echo "${SCENARIO}: mountpoint $*" >>"${TRACE_FILE}"
# Handle: mountpoint -q -- <path>  or  mountpoint <path>
p=""; quiet=0
for a in "$@"; do
  case "$a" in
    -q) quiet=1 ;;
    --) ;;
    -*) ;;
    *) p="$a" ;;
  esac
done
for _mp in ${_MOUNT_RETURN_0:-}; do
  if [ "$p" = "$_mp" ]; then exit 0; fi
done
exit 1
MPEOF
chmod +x "$_FAKE_BIN/mountpoint"

# -- gosu --
cat >"$_FAKE_BIN/gosu" <<'GOSUEOF'
#!/bin/bash
user="$1"; shift
echo "${SCENARIO}: gosu $user $*" >>"${TRACE_FILE}"
exec "$@"
GOSUEOF
chmod +x "$_FAKE_BIN/gosu"

# -- python3 (installer) --
cat >"$_FAKE_BIN/python3" <<'PYEOF'
#!/bin/bash
echo "${SCENARIO}: python3 $*" >>"${TRACE_FILE}"
if [ "${_INSTALLER_FAIL:-0}" = "1" ]; then exit 1; fi
exit 0
PYEOF
chmod +x "$_FAKE_BIN/python3"

# -- rtk --
cat >"$_FAKE_BIN/rtk" <<'RTKEOF'
#!/bin/bash
echo "${SCENARIO}: rtk $*" >>"${TRACE_FILE}"
if [ "$1" = "init" ] && [ "${_RTK_INIT_FAIL:-0}" = "1" ]; then exit 1; fi
if [ "$1" = "telemetry" ] && [ "${_RTK_TELEMETRY_FAIL:-0}" = "1" ]; then exit 1; fi
exit 0
RTKEOF
chmod +x "$_FAKE_BIN/rtk"

# -- git --
cat >"$_FAKE_BIN/git" <<'GITEOF'
#!/bin/bash
echo "${SCENARIO}: git $*" >>"${TRACE_FILE}"
exit 0
GITEOF
chmod +x "$_FAKE_BIN/git"

# -- chown, chmod, find --
for _cmd in chown chmod find; do
  cat >"$_FAKE_BIN/$_cmd" <<CMDEOF
#!/bin/bash
echo "\${SCENARIO}: $_cmd \$*" >>"\${TRACE_FILE}"
exit 0
CMDEOF
  chmod +x "$_FAKE_BIN/$_cmd"
done

# ═══════════════════════════════════════════════════════════════════════
# Bash-builtin shadows (functions override builtins)
# ═══════════════════════════════════════════════════════════════════════

exec() {
  _trace_line "exec $*"
  return 0
}

command() {
  _trace_line "command $*"
  return 0
}

# ═══════════════════════════════════════════════════════════════════════
# Sandbox paths — mechanically substitute fixed paths in the real
# entrypoint with temp directories we control.
# ═══════════════════════════════════════════════════════════════════════

# Pi-home sandbox: provided by the Python driver via _PI_HOME_SANDBOX.
# If set and non-empty, classified as a mount so the entrypoint's
# `is_mount_point` returns true for it.
if [ -n "${_PI_HOME_SANDBOX:-}" ]; then
  _MOUNT_RETURN_0="${_MOUNT_RETURN_0:-} ${_PI_HOME_SANDBOX}"
  export _MOUNT_RETURN_0
fi

# Projection file: copied to a temp path then substituted in.
_PROJ_FIXED="$(mktemp)"
if [ -n "${_PROJECTION_FILE:-}" ] && [ -f "$_PROJECTION_FILE" ]; then
  cp "$_PROJECTION_FILE" "$_PROJ_FIXED"
else
  rm -f "$_PROJ_FIXED" 2>/dev/null || true
fi

# ── source the real entrypoint with two mechanical substitutions ─────
#   1. RUNTIME_PROJECTION path → temp file
#   2. /home/dev/.pi                → pi-home sandbox (if provided)
# Control flow, functions, if-blocks, exit/exec are 100% genuine.
_HOME_SUBST="${_PI_HOME_SANDBOX:-/home/dev/.pi}"
set +e
(
  source <(
    sed \
      -e 's|RUNTIME_PROJECTION="/run/pi-cli/docker-constructor.runtime.toml"|RUNTIME_PROJECTION="'"$_PROJ_FIXED"'"|' \
      -e 's|/home/dev/.pi|'"$_HOME_SUBST"'|g' \
      "$ENTRYPOINT_REAL"
  ) /bin/true
) >/dev/null 2>/dev/null
_EP_RC=$?
set -e

_trace_line "exit_code $_EP_RC"

# ═══════════════════════════════════════════════════════════════════════
# Dump trace
# ═══════════════════════════════════════════════════════════════════════
echo "=== HARNESS TRACE BEGIN ==="
cat "$TRACE_FILE"
echo "=== HARNESS TRACE END ==="
