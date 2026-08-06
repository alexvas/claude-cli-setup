#!/usr/bin/env bash
set -u

if (($# == 0)); then
  echo "usage: $0 <command> [args...]" >&2
  exit 2
fi

was_enabled="$(nmcli -t -f NETWORKING general status)"
restore() {
  if [[ "$was_enabled" == "enabled" ]]; then
    nmcli networking on || true
  fi
}
trap restore EXIT INT TERM

nmcli networking off || {
  echo "$0: nmcli networking off failed — refusing to run without isolation" >&2
  exit 1
}
"$@"
