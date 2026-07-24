#!/usr/bin/env bash
# verify-decouple-build-runtime.sh
# Docker-host verification for the "decouple-docker-build-from-runtime-mounts" change.
#
# Usage:
#   bash openspec/changes/decouple-docker-build-from-runtime-mounts/verify.sh
#
# The script runs automated checks and creates one manual-check template.
# After completing the manual step, write PASS or FAIL into the file:
#   openspec/changes/decouple-docker-build-from-runtime-mounts/verification/manual-3-3b.txt
#
# Then re-run this script.  It will pick up the manual result from that
# stable location and (if all checks pass) exit 0 with ALL CHECKS PASSED.
#
# Saves timestamped artefacts under:
#   openspec/changes/decouple-docker-build-from-runtime-mounts/verification/<iso-date>/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CHANGE_DIR="$SCRIPT_DIR"
RUN_ID="$(date -Iseconds | tr : -)"
EVIDENCE_DIR="$CHANGE_DIR/verification/$RUN_ID"

# Stable manual-result file — lives outside the timestamped directory so it
# survives across re-runs.
MANUAL_3_3B="$CHANGE_DIR/verification/manual-3-3b.txt"

PASS=0
FAIL=0
TOTAL=0
MANUAL_PENDING=0

# ---- cleanup ---------------------------------------------------------------

_cleanup_rc=0
_cleanup_files=()

_cleanup() {
    _cleanup_rc=$?
    local f
    for f in "${_cleanup_files[@]}"; do
        rm -rf "$f" 2>/dev/null || true
    done
    return $_cleanup_rc
}
trap _cleanup EXIT

_reg_cleanup() {
    _cleanup_files+=("$1")
}

# ---- helpers ---------------------------------------------------------------

_evidence() {
    echo "$1=$2" >> "$EVIDENCE_DIR/summary.txt"
}

_section() {
    { echo
      echo "========================================"
      echo "  $*"
      echo "========================================"
      echo
    } >> "$EVIDENCE_DIR/report.txt"
    echo >&2
    echo "=== $* ===" >&2
}

# _log — display helper.  Call AFTER incrementing TOTAL; uses $TOTAL as the
#        stable check number for both console and filenames.
_log() {
    local desc="$1"; shift
    echo ">>> $desc"                              >> "$EVIDENCE_DIR/report.txt"
    echo ">>> \$ $*"                              >> "$EVIDENCE_DIR/report.txt"
    echo                                          >> "$EVIDENCE_DIR/report.txt"
    echo "[$TOTAL] $desc" >&2
}

_run() {
    local desc="$1"; shift
    TOTAL=$((TOTAL + 1))
    _log "$desc" "$@"
    local rc=0
    "$@" > "$EVIDENCE_DIR/$TOTAL.stdout" 2> "$EVIDENCE_DIR/$TOTAL.stderr" || rc=$?
    echo "$rc" > "$EVIDENCE_DIR/$TOTAL.rc"
    _evidence "check_$TOTAL" "$desc"
    _evidence "check_${TOTAL}_rc" "$rc"
    if [ "$rc" -eq 0 ]; then
        echo ">>> RESULT: PASS (exit 0)"          >> "$EVIDENCE_DIR/report.txt"
        echo "    PASS" >&2
        PASS=$((PASS + 1))
    else
        echo ">>> RESULT: **FAIL** (exit $rc)"    >> "$EVIDENCE_DIR/report.txt"
        echo ">>> stderr (last 40 lines):"        >> "$EVIDENCE_DIR/report.txt"
        tail -40 "$EVIDENCE_DIR/$TOTAL.stderr"    >> "$EVIDENCE_DIR/report.txt"
        echo "    **FAIL** (exit $rc)" >&2
        FAIL=$((FAIL + 1))
    fi
    echo >> "$EVIDENCE_DIR/report.txt"
}

_expect_failure() {
    local desc="$1"
    local stderr_pattern="$2"
    shift 2
    TOTAL=$((TOTAL + 1))
    _log "$desc (expect non-zero, stderr ~ $stderr_pattern)" "$@"
    local rc=0
    "$@" > "$EVIDENCE_DIR/$TOTAL.stdout" 2> "$EVIDENCE_DIR/$TOTAL.stderr" || rc=$?
    echo "$rc" > "$EVIDENCE_DIR/$TOTAL.rc"
    _evidence "check_$TOTAL" "$desc"
    _evidence "check_${TOTAL}_rc" "$rc"
    if [ "$rc" -eq 0 ]; then
        echo ">>> RESULT: **FAIL** (exit 0 — should have been rejected)" >> "$EVIDENCE_DIR/report.txt"
        echo "    **FAIL** (should have been rejected)" >&2
        FAIL=$((FAIL + 1))
    elif grep -qE "$stderr_pattern" "$EVIDENCE_DIR/$TOTAL.stderr"; then
        echo ">>> RESULT: PASS (exit $rc — stderr matches \"$stderr_pattern\")" >> "$EVIDENCE_DIR/report.txt"
        echo "    PASS (rejected: exit $rc)" >&2
        PASS=$((PASS + 1))
    else
        echo ">>> RESULT: **FAIL** (exit $rc but stderr missing \"$stderr_pattern\")" >> "$EVIDENCE_DIR/report.txt"
        echo ">>> stderr (last 40 lines):"        >> "$EVIDENCE_DIR/report.txt"
        tail -40 "$EVIDENCE_DIR/$TOTAL.stderr"    >> "$EVIDENCE_DIR/report.txt"
        echo "    **FAIL** (wrong rejection reason)" >&2
        FAIL=$((FAIL + 1))
    fi
    echo >> "$EVIDENCE_DIR/report.txt"
}

# _manual — a check that must be confirmed via the stable manual-result file.
# On the first run the template is written there.  The user edits it and
# re-runs; subsequent runs pick up PASS or FAIL from the stable file.
_manual() {
    local desc="$1"; shift
    TOTAL=$((TOTAL + 1))
    local result_file="$MANUAL_3_3B"

    if [ -f "$result_file" ]; then
        local result
        result="$(head -1 "$result_file" | tr -d '[:space:]')"
        case "$result" in
            PASS)
                echo ">>> $desc"                              >> "$EVIDENCE_DIR/report.txt"
                echo ">>> RESULT: PASS (confirmed in $result_file)" >> "$EVIDENCE_DIR/report.txt"
                echo                                 >> "$EVIDENCE_DIR/report.txt"
                echo "    PASS (manual confirmed)" >&2
                _evidence "check_$TOTAL" "$desc"
                _evidence "check_${TOTAL}_rc" "0"
                PASS=$((PASS + 1))
                ;;
            FAIL)
                echo ">>> $desc"                              >> "$EVIDENCE_DIR/report.txt"
                echo ">>> RESULT: **FAIL** (confirmed in $result_file)" >> "$EVIDENCE_DIR/report.txt"
                echo                                 >> "$EVIDENCE_DIR/report.txt"
                echo "    **FAIL** (manual confirmed)" >&2
                _evidence "check_$TOTAL" "$desc"
                _evidence "check_${TOTAL}_rc" "1"
                FAIL=$((FAIL + 1))
                ;;
            *)
                _manual_pending "$desc" "$result_file" "$@"
                ;;
        esac
    else
        _manual_pending "$desc" "$result_file" "$@"
    fi
}

_manual_pending() {
    local desc="$1" result_file="$2"; shift 2
    MANUAL_PENDING=$((MANUAL_PENDING + 1))
    {
        echo ">>> $desc"
        echo ">>> STATUS: MANUAL — not yet confirmed"
        echo ">>> Result file: $result_file"
        echo ">>> Instructions:"
        printf '>>>   %s\n' "$@"
        echo ">>>"
        echo ">>> After completing, write PASS or FAIL on the first line of:"
        echo ">>>   $result_file"
        echo ">>> Then re-run:  bash $0"
        echo
    } >> "$EVIDENCE_DIR/report.txt"
    echo "    MANUAL PENDING: $desc" >&2
    _evidence "check_$TOTAL" "$desc"
    _evidence "check_${TOTAL}_rc" "manual_pending"

    # Write the template (only if it doesn't exist yet).
    if [ ! -f "$result_file" ]; then
        {
            echo "# Replace this line with PASS or FAIL, then re-run verify.sh"
            echo "#"
            printf '#   %s\n' "$@"
        } > "$result_file"
    fi
}

# ---- init ------------------------------------------------------------------

mkdir -p "$EVIDENCE_DIR"

{
    echo "decouple-docker-build-from-runtime-mounts — Verification Report"
    echo "Run:    $(date -Iseconds)"
    echo "Host:   $(hostname)"
    echo "User:   $(whoami)"
    echo "Repo:   $REPO_ROOT"
    echo "Evidence: $EVIDENCE_DIR"
    echo
    echo "Versions"
    echo "--------"
    docker --version 2>&1        || echo "docker: NOT FOUND"
    docker compose version 2>&1  || echo "docker compose: NOT FOUND"
    python3 --version 2>&1       || echo "python3: NOT FOUND"
    echo
    echo "Sanity"
    echo "------"
    echo "docker-compose.yml: $(wc -c < "$REPO_ROOT/docker-compose.yml") bytes"
    echo "docker-compose.runtime.yml: $(wc -c < "$REPO_ROOT/docker-compose.runtime.yml") bytes"
    echo "cd into: $REPO_ROOT"
    echo
} > "$EVIDENCE_DIR/report.txt"

cd "$REPO_ROOT"

# ---- preserve rootless-Docker env -----------------------------------------
# env -i strips everything; DOCKER_HOST points to the actual socket when
# using rootless Docker (e.g. unix:///run/user/1000/docker.sock).
_DOCKER_HOST="${DOCKER_HOST:-}"
_XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-}"
_evidence "DOCKER_HOST" "$_DOCKER_HOST"
_evidence "XDG_RUNTIME_DIR" "$_XDG_RUNTIME_DIR"

# ---- isolation -------------------------------------------------------------

ISOLATED_HOME="$(mktemp -d)"
_reg_cleanup "$ISOLATED_HOME"
export HOME="$ISOLATED_HOME"
mkdir -p "$ISOLATED_HOME/.pi"
_evidence "isolated_home" "$ISOLATED_HOME"

# ---- temp dirs outside repo for additional project -------------------------

ADD_PROJ="$(mktemp -d)"
_reg_cleanup "$ADD_PROJ"
mkdir -p "$ADD_PROJ/subdir"
chmod 755 "$ADD_PROJ"
echo "additional project file" > "$ADD_PROJ/README.txt"
chmod 644 "$ADD_PROJ/README.txt"
_evidence "add_proj" "$ADD_PROJ"

# ---- compose fragment for PROJECT_PATH_2 mount -----------------------------

ADD_FRAGMENT="$(mktemp)"
_reg_cleanup "$ADD_FRAGMENT"
cat > "$ADD_FRAGMENT" <<'YAML'
services:
  pi:
    volumes:
      - ${PROJECT_PATH_2:?set PROJECT_PATH_2}:${PROJECT_PATH_2:?set PROJECT_PATH_2}
YAML
_evidence "add_fragment" "$ADD_FRAGMENT"

# ---- 1.1 — Build without project configuration -----------------------------

_section "1.1: Build succeeds without .env, PROJECT_PATH_*, COMPOSE_FILE"

_run "1.1 - compose build pi (no .env, no project vars)" \
    env -i PATH="$PATH" HOME="$HOME" USER="${USER:-}" \
        DOCKER_HOST="$_DOCKER_HOST" XDG_RUNTIME_DIR="$_XDG_RUNTIME_DIR" \
        COMPOSE_DISABLE_ENV_FILE=1 \
        python3 docker/versions.py compose build pi

# ---- 1.2 — Runtime rejection / acceptance ----------------------------------

_section "1.2: Runtime rejects missing project, accepts with project set"

_expect_failure "1.2a - compose run pi WITHOUT PROJECT_PATH_1" \
    "PROJECT_PATH_1" \
    env -i PATH="$PATH" HOME="$HOME" \
        DOCKER_HOST="$_DOCKER_HOST" XDG_RUNTIME_DIR="$_XDG_RUNTIME_DIR" \
        COMPOSE_DISABLE_ENV_FILE=1 \
        python3 docker/versions.py compose run --rm pi

_expect_failure "1.2b - compose config WITHOUT PROJECT_PATH_1" \
    "PROJECT_PATH_1" \
    env -i PATH="$PATH" HOME="$HOME" \
        DOCKER_HOST="$_DOCKER_HOST" XDG_RUNTIME_DIR="$_XDG_RUNTIME_DIR" \
        COMPOSE_DISABLE_ENV_FILE=1 \
        python3 docker/versions.py compose config

_run "1.2c - compose config WITH PROJECT_PATH_1 and PROJECT_PATH_2 fragment" \
    env -i PATH="$PATH" HOME="$HOME" \
        DOCKER_HOST="$_DOCKER_HOST" XDG_RUNTIME_DIR="$_XDG_RUNTIME_DIR" \
        COMPOSE_DISABLE_ENV_FILE=1 \
        COMPOSE_FILE="docker-compose.yml:docker-compose.runtime.yml:$ADD_FRAGMENT" \
        PROJECT_PATH_1="$REPO_ROOT" \
        PROJECT_PATH_2="$ADD_PROJ" \
        python3 docker/versions.py compose config

_run "1.2d - compose run --rm pi with mount + pwd + mountpoint checks" \
    env -i PATH="$PATH" HOME="$HOME" \
        DOCKER_HOST="$_DOCKER_HOST" XDG_RUNTIME_DIR="$_XDG_RUNTIME_DIR" \
        COMPOSE_DISABLE_ENV_FILE=1 \
        COMPOSE_FILE="docker-compose.yml:docker-compose.runtime.yml:$ADD_FRAGMENT" \
        PROJECT_PATH_1="$REPO_ROOT" \
        PROJECT_PATH_2="$ADD_PROJ" \
        CHOWN_WORK_ON_START=0 \
        python3 docker/versions.py compose run -T --rm pi \
            sh -euc '
                echo "pwd=$(pwd)"
                [ "$(pwd)" = "$PROJECT_PATH_1" ] || { echo "FAIL: pwd=$(pwd) expected=$PROJECT_PATH_1"; exit 1; }
                echo "OK: working_dir matches PROJECT_PATH_1"

                grep -qF " $PROJECT_PATH_1 " /proc/mounts || { echo "FAIL: $PROJECT_PATH_1 is not a mount"; exit 1; }
                echo "OK: main mount exists"

                test -f "$PROJECT_PATH_1/docker-compose.yml" || { echo "FAIL: repo files not visible in main mount"; exit 1; }
                echo "OK: main mount has repo content"

                grep -qF " $PROJECT_PATH_2 " /proc/mounts || { echo "FAIL: $PROJECT_PATH_2 is not a mount"; exit 1; }
                echo "OK: additional mount exists"

                ls -la "$PROJECT_PATH_2/" || true
                test -f "$PROJECT_PATH_2/README.txt" || { echo "FAIL: additional project files not visible"; exit 1; }
                echo "OK: additional mount has expected files"
                echo "ALL MOUNT CHECKS PASSED"
            '

# ---- 3.2 — Build + verify image --------------------------------------------

_section "3.2: Build without project config, verify resulting image"

IMAGE_TAG="pi-cli-decouple-test:latest"

_run "3.2a - tag built image" \
    docker tag pi-cli-pi:latest "$IMAGE_TAG"

_run "3.2b - verify-runtime.sh on built image" \
    sh docker/verify-runtime.sh "$IMAGE_TAG"

_run "3.2c - cleanup test tag" \
    docker rmi "$IMAGE_TAG"

# ---- 3.3 — Launcher --------------------------------------------------------

_section "3.3: Launcher — COMPOSE_FILE chain and main 1:1 mount"

# Automated: verify COMPOSE_FILE_RUNTIME is defined and wired into the chain.
TOTAL=$((TOTAL + 1))
LAUNCHER="$REPO_ROOT/launch-pi.py"
{
    echo ">>> 3.3a - launcher source defines COMPOSE_FILE_RUNTIME and uses it in COMPOSE_FILE"
    if grep -q "COMPOSE_FILE_RUNTIME" "$LAUNCHER" && \
       grep -q 'str(COMPOSE_FILE_RUNTIME)' "$LAUNCHER"; then
        echo ">>> RESULT: PASS — COMPOSE_FILE_RUNTIME defined and used in COMPOSE_FILE chain"
        echo "    PASS" >&2
        _evidence "check_$TOTAL" "launcher defines COMPOSE_FILE_RUNTIME"
        _evidence "check_${TOTAL}_rc" "0"
        PASS=$((PASS + 1))
    else
        echo ">>> RESULT: **FAIL** — COMPOSE_FILE_RUNTIME not found or not used"
        echo "    **FAIL**" >&2
        _evidence "check_$TOTAL" "launcher defines COMPOSE_FILE_RUNTIME"
        _evidence "check_${TOTAL}_rc" "1"
        FAIL=$((FAIL + 1))
    fi
    echo
} >> "$EVIDENCE_DIR/report.txt"
echo "[$TOTAL] 3.3a - launcher source check" >&2

_manual "3.3b - launch with TUI, verify mounts inside container" \
  "Run:  cd $REPO_ROOT && uv run launch-pi.py --tui" \
  "Select a main project and at least one additional project, then press F5/r." \
  "Inside the launched container, verify:" \
  "  pwd = selected main project path" \
  "  ls <main-project>       shows project files (main 1:1 mount works)" \
  "  ls <additional-project> shows project files (additional mount works)" \
  "Exit container. Run again, press Esc/q at TUI — must exit with 'No project selected'." \
  "After verification, write PASS or FAIL into the first line of:" \
  "  $MANUAL_3_3B" \
  "Then re-run:  bash $0"

# ---- summary ----------------------------------------------------------------

_section "SUMMARY"

VERDICT=""
if [ "$FAIL" -eq 0 ] && [ "$MANUAL_PENDING" -eq 0 ]; then
    VERDICT="VERDICT: ALL CHECKS PASSED"
elif [ "$FAIL" -eq 0 ]; then
    VERDICT="VERDICT: AUTOMATED CHECKS PASSED — $MANUAL_PENDING manual check(s) pending"
else
    VERDICT="VERDICT: $FAIL FAILURE(S)"
fi

{
    echo "Total checks:      $TOTAL"
    echo "Passed:            $PASS"
    echo "Failed:            $FAIL"
    echo "Manual pending:    $MANUAL_PENDING"
    echo
    echo "$VERDICT"
    echo
    echo "Artefacts: $EVIDENCE_DIR/"
    echo "  report.txt       — full human-readable report"
    echo "  summary.txt      — key=value machine-readable summary"
    echo "  N.stdout          — stdout for check N"
    echo "  N.stderr          — stderr for check N"
    echo "  N.rc              — return code for check N"
    echo
    echo "Manual result (stable, survives re-runs):"
    echo "  $MANUAL_3_3B"
} | tee -a "$EVIDENCE_DIR/report.txt"

if [ "$FAIL" -gt 0 ] || [ "$MANUAL_PENDING" -gt 0 ]; then
    exit 1
fi
exit 0
