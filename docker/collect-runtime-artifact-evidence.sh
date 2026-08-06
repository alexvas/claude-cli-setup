#!/usr/bin/env bash
# Collect host-side evidence for one real runtime-artifact launch.
#
# The script deliberately uses a private HOME beneath the evidence directory
# unless --pi-home is supplied. It does not alter the artifact cache and does
# not enable project ownership repair. Network policy is owned by the caller:
# run once with cache misses allowed, then run again with registry access
# disabled to collect cache-hit/offline evidence.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: docker/collect-runtime-artifact-evidence.sh [options]

Run one Docker constructor launch and write logs, cache metadata, and live
container mount evidence to a timestamped evidence directory.

Options:
  --output-dir DIR       Evidence directory (default: .docker-generated/evidence/runtime-artifacts-<UTC timestamp>)
  --main-project DIR     Main project to mount (default: repository root)
  --pi-home DIR          Pi home to mount; path must end in /.pi (default: DIR/home/.pi)
  --image IMAGE          Runtime image (default: pi-cli-pi:latest)
  --override KEY=VALUE   Runtime override to pass to run (repeatable)
  --duration SECONDS     Keep container alive for inspection (default: 30)
  -h, --help             Show this help text

The command does not build an image, clear the artifact cache, alter the
reviewed inventory, or block network access. Preserve each output directory as
an acceptance-evidence run; redact it before sharing.
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir=""
main_project="$repo_root"
pi_home=""
image="pi-cli-pi:latest"
overrides=()
duration=30

while (($#)); do
  case "$1" in
    --output-dir)
      output_dir=${2:?--output-dir requires a directory}
      shift 2
      ;;
    --main-project)
      main_project=${2:?--main-project requires a directory}
      shift 2
      ;;
    --pi-home)
      pi_home=${2:?--pi-home requires a directory}
      shift 2
      ;;
    --image)
      image=${2:?--image requires an image name}
      shift 2
      ;;
    --override)
      overrides+=("${2:?--override requires KEY=VALUE}")
      shift 2
      ;;
    --duration)
      duration=${2:?--duration requires seconds}
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$duration" =~ ^[1-9][0-9]*$ ]]; then
  printf '%s\n' '--duration must be a positive integer' >&2
  exit 2
fi

main_project="$(cd "$main_project" && pwd)"
if [[ -z "$output_dir" ]]; then
  output_dir="$repo_root/.docker-generated/evidence/runtime-artifacts-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"

if [[ -z "$pi_home" ]]; then
  pi_home="$output_dir/home/.pi"
fi
mkdir -p "$pi_home"
pi_home="$(cd "$pi_home" && pwd)"
if [[ "$(basename "$pi_home")" != ".pi" ]]; then
  printf '%s\n' '--pi-home must name a .pi directory because run derives it from HOME' >&2
  exit 2
fi
home_dir="$(dirname "$pi_home")"
cache_root="$repo_root/.docker-generated/runtime-artifacts/blobs"

for command in docker python3; do
  if ! command -v "$command" >/dev/null 2>&1; then
    printf 'Required command not found: %s\n' "$command" >&2
    exit 127
  fi
done

docker info >/dev/null

printf '%s\n' "$image" >"$output_dir/image.txt"
printf '%s\n' "$main_project" >"$output_dir/main-project.txt"
printf '%s\n' "$pi_home" >"$output_dir/pi-home.txt"
printf '%s\n' "$cache_root" >"$output_dir/cache-root.txt"
printf '%s\n' "$duration" >"$output_dir/inspection-duration-seconds.txt"
date -u +%Y-%m-%dT%H:%M:%SZ >"$output_dir/started-at.txt"
docker version >"$output_dir/docker-version.txt" 2>&1 || true
docker image inspect "$image" >"$output_dir/image-inspect.json" 2>&1 || true

snapshot_cache() {
  local destination=$1
  if [[ -d "$cache_root" ]]; then
    find "$cache_root" -xdev -type f -printf '%m %s %T@ %p\n' \
      | LC_ALL=C sort >"$destination"
  else
    : >"$destination"
  fi
}

snapshot_cache "$output_dir/cache-before.txt"
docker ps -q --filter "ancestor=$image" | LC_ALL=C sort >"$output_dir/containers-before.txt"

run_args=(
  "$repo_root/docker/docker-constructor.py" run
  --image "$image"
  --main-project "$main_project"
  --no-tty
  --no-interactive
  --chown-on-start 0
)
for override in "${overrides[@]}"; do
  run_args+=(--override "$override")
done
run_args+=(-- sh -lc "sleep $duration")
printf '%q ' "${run_args[@]}" >"$output_dir/constructor-command.txt"
printf '\n' >>"$output_dir/constructor-command.txt"

launch_pid=""
cleanup() {
  if [[ -n "$launch_pid" ]] && kill -0 "$launch_pid" 2>/dev/null; then
    kill "$launch_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

(
  cd "$repo_root"
  HOME="$home_dir" "${run_args[@]}"
) >"$output_dir/constructor.stdout.log" 2>"$output_dir/constructor.stderr.log" &
launch_pid=$!

container_id=""
for _ in $(seq 1 60); do
  while IFS= read -r candidate; do
    if ! grep -qxF "$candidate" "$output_dir/containers-before.txt"; then
      container_id=$candidate
      break 2
    fi
  done < <(docker ps -q --filter "ancestor=$image" | LC_ALL=C sort)
  sleep 1
done

if [[ -n "$container_id" ]]; then
  printf '%s\n' "$container_id" >"$output_dir/container-id.txt"
  docker inspect "$container_id" >"$output_dir/container-inspect.json"
  docker inspect "$container_id" \
    --format '{{range .Mounts}}{{println .Source "->" .Destination "RW=" .RW}}{{end}}' \
    >"$output_dir/container-mounts.txt"
  docker logs "$container_id" >"$output_dir/container.stdout.log" 2>"$output_dir/container.stderr.log" || true
  docker exec "$container_id" sh -lc '
    id
    printf "\\n-- artifact mounts --\\n"
    grep "/run/pi-cli/runtime-artifacts" /proc/self/mountinfo || true
    printf "\\n-- mounted artifact files --\\n"
    find /run/pi-cli/runtime-artifacts -type f -printf "%m %s %p\\n" 2>/dev/null || true
  ' >"$output_dir/container-runtime-state.txt" 2>&1 || true
else
  : >"$output_dir/container-id.txt"
  : >"$output_dir/container-mounts.txt"
  printf '%s\n' 'No running container was found during the inspection window.' \
    >"$output_dir/inspection-warning.txt"
fi

set +e
wait "$launch_pid"
launch_status=$?
set -e
launch_pid=""
printf '%s\n' "$launch_status" >"$output_dir/constructor-exit-status.txt"
snapshot_cache "$output_dir/cache-after.txt"
date -u +%Y-%m-%dT%H:%M:%SZ >"$output_dir/finished-at.txt"
trap - EXIT INT TERM

printf 'Evidence written to: %s\n' "$output_dir"
printf 'Constructor exit status: %s\n' "$launch_status"
exit "$launch_status"
