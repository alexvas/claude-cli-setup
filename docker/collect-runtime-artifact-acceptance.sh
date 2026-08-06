#!/usr/bin/env bash
# Coordinate real-Docker runtime-artifact acceptance scenarios.
#
# Each scenario delegates to collect-runtime-artifact-evidence.sh and receives
# its own evidence directory and isolated Pi home. The optional offline wrapper
# is deliberately caller-supplied: network isolation is host policy and must
# not be guessed or implemented with unsafe firewall mutations here.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: docker/collect-runtime-artifact-acceptance.sh [options]

Collect one or more real-Docker runtime-artifact acceptance scenarios below a
single evidence root:

  00-build/                    optional one-time image build evidence
  01-first-materialization/    normal cache-miss launch
  02-cache-hit-offline/        cache-hit launch through --offline-wrapper
  03-runtime-override/         optional reviewed runtime override launch
  04-corrupt-cache-recovery/   optional corrupt-cache recovery launch

Options:
  --output-dir DIR       Evidence root (default: .docker-generated/evidence/runtime-artifacts-acceptance-<UTC timestamp>)
  --main-project DIR     Main project to mount (default: repository root)
  --image IMAGE          Runtime image/tag (default: pi-cli-pi:latest)
  --duration SECONDS     Per-launch inspection window (default: 30)
  --build                Build the image once before launch scenarios
  --fresh-cache          Remove generated runtime cache before scenario 01
  --offline-wrapper PATH Executable that applies offline policy, then execs its arguments
  --override KEY=VALUE   Reviewed runtime override for scenario 03 (repeatable)
  --recover-corrupt-cache
                         Corrupt one generated cache blob, then collect recovery evidence
  -h, --help             Show this help text

The coordinator never changes the reviewed inventory. --recover-corrupt-cache
only changes .docker-generated/runtime-artifacts and requires network access
for the following recovery launch. The offline wrapper must be an executable
that receives the evidence collector command and its arguments, for example:

  #!/usr/bin/env bash
  apply_my_registry_block_policy
  exec "$@"
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
collector="$repo_root/docker/collect-runtime-artifact-evidence.sh"
output_dir=""
main_project="$repo_root"
image="pi-cli-pi:latest"
duration=30
collect_build=false
fresh_cache=false
offline_wrapper=""
overrides=()
recover_corrupt_cache=false

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
    --image)
      image=${2:?--image requires an image name}
      shift 2
      ;;
    --duration)
      duration=${2:?--duration requires seconds}
      shift 2
      ;;
    --build)
      collect_build=true
      shift
      ;;
    --fresh-cache)
      fresh_cache=true
      shift
      ;;
    --offline-wrapper)
      offline_wrapper=${2:?--offline-wrapper requires an executable path}
      shift 2
      ;;
    --override)
      overrides+=("${2:?--override requires KEY=VALUE}")
      shift 2
      ;;
    --recover-corrupt-cache)
      recover_corrupt_cache=true
      shift
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
if [[ ! -x "$collector" ]]; then
  printf 'Evidence collector is not executable: %s\n' "$collector" >&2
  exit 1
fi
if [[ -n "$offline_wrapper" && ! -x "$offline_wrapper" ]]; then
  printf 'Offline wrapper is not executable: %s\n' "$offline_wrapper" >&2
  exit 2
fi

main_project="$(cd "$main_project" && pwd)"
if [[ -z "$output_dir" ]]; then
  output_dir="$repo_root/.docker-generated/evidence/runtime-artifacts-acceptance-$(date -u +%Y%m%dT%H%M%SZ)"
fi
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
printf '%s\n' "$image" >"$output_dir/image.txt"
printf '%s\n' "$main_project" >"$output_dir/main-project.txt"
printf '%s\n' "$duration" >"$output_dir/inspection-duration-seconds.txt"
date -u +%Y-%m-%dT%H:%M:%SZ >"$output_dir/started-at.txt"

run_scenario() {
  local name=$1
  shift
  local scenario_dir="$output_dir/$name"
  local -a args=(
    "$collector"
    --output-dir "$scenario_dir"
    --main-project "$main_project"
    --image "$image"
    --duration "$duration"
  )
  args+=("$@")
  printf 'Collecting %s\n' "$name"
  "${args[@]}"
}

if [[ "$collect_build" == true ]]; then
  build_dir="$output_dir/00-build"
  mkdir -p "$build_dir"
  printf '%q ' "$repo_root/docker/docker-constructor.py" build --tag "$image" --yes --progress plain \
    >"$build_dir/constructor-command.txt"
  printf '\n' >>"$build_dir/constructor-command.txt"
  (
    cd "$repo_root"
    "$repo_root/docker/docker-constructor.py" build \
      --tag "$image" --yes --progress plain
  ) >"$build_dir/constructor.stdout.log" 2>"$build_dir/constructor.stderr.log"
  printf '%s\n' "$?" >"$build_dir/constructor-exit-status.txt"
fi

if [[ "$fresh_cache" == true ]]; then
  cache_root="$repo_root/.docker-generated/runtime-artifacts"
  rm -rf "$cache_root"
  printf '%s\n' "$cache_root" >"$output_dir/cache-cleared-before-scenario-01.txt"
else
  printf '%s\n' 'Cache was retained; scenario 01 may be a cache hit.' \
    >"$output_dir/01-first-materialization.CACHE-RETAINED.txt"
fi

run_scenario 01-first-materialization

if [[ -n "$offline_wrapper" ]]; then
  printf 'Collecting 02-cache-hit-offline\n'
  "$offline_wrapper" "$collector" \
    --output-dir "$output_dir/02-cache-hit-offline" \
    --main-project "$main_project" \
    --image "$image" \
    --duration "$duration"
else
  printf '%s\n' 'Skipped: pass --offline-wrapper to collect cache-hit offline evidence.' \
    >"$output_dir/02-cache-hit-offline.SKIPPED.txt"
fi

if ((${#overrides[@]})); then
  override_args=()
  for override in "${overrides[@]}"; do
    override_args+=(--override "$override")
  done
  run_scenario 03-runtime-override "${override_args[@]}"
else
  printf '%s\n' 'Skipped: pass one or more --override KEY=VALUE values for reviewed override evidence.' \
    >"$output_dir/03-runtime-override.SKIPPED.txt"
fi

if [[ "$recover_corrupt_cache" == true ]]; then
  blob="$(awk '$2 == "->" && $3 ~ /^\/run\/pi-cli\/runtime-artifacts\// {print $1; exit}' \
    "$output_dir/01-first-materialization/container-mounts.txt")"
  if [[ -z "$blob" || ! -f "$blob" ]]; then
    printf '%s\n' 'No selected artifact mount source is available to corrupt.' >&2
    exit 1
  fi
  mkdir -p "$output_dir/04-corrupt-cache-recovery"
  printf '%s\n' "$blob" >"$output_dir/04-corrupt-cache-recovery/corrupted-blob.txt"
  chmod u+w "$blob"
  printf 'intentionally corrupt acceptance fixture\n' >"$blob"
  chmod 400 "$blob"
  run_scenario 04-corrupt-cache-recovery
else
  printf '%s\n' 'Skipped: pass --recover-corrupt-cache to collect recovery evidence.' \
    >"$output_dir/04-corrupt-cache-recovery.SKIPPED.txt"
fi

date -u +%Y-%m-%dT%H:%M:%SZ >"$output_dir/finished-at.txt"
printf 'Acceptance evidence written to: %s\n' "$output_dir"
