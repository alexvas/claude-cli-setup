#!/bin/bash
# Ensure user "dev" exists with DEV_UID / group dev with DEV_GID.
set -euo pipefail

DEV_UID="${DEV_UID:-1000}"
DEV_GID="${DEV_GID:-${DEV_UID}}"

ensure_dev_group() {
  if getent group dev >/dev/null 2>&1; then
    current_gid="$(getent group dev | cut -d: -f3)"
    if [ "${current_gid}" != "${DEV_GID}" ]; then
      groupmod -g "${DEV_GID}" dev 2>/dev/null || true
    fi
    return 0
  fi

  if existing_group="$(getent group "${DEV_GID}" | cut -d: -f1)" && [ -n "${existing_group}" ]; then
    groupmod -n dev "${existing_group}" 2>/dev/null || groupadd -g "${DEV_GID}" dev
  else
    groupadd -g "${DEV_GID}" dev
  fi
}

ensure_dev_group

if id dev >/dev/null 2>&1; then
  usermod -u "${DEV_UID}" -g dev dev 2>/dev/null || true
  chown -R dev:dev /home/dev 2>/dev/null || true
  exit 0
fi

if existing="$(getent passwd "${DEV_UID}" | cut -d: -f1)" && [ -n "${existing}" ] && [ "${existing}" != "dev" ]; then
  mkdir -p /home/dev
  if [ -d "/home/${existing}" ] && [ "$(ls -A "/home/${existing}" 2>/dev/null | wc -l)" -gt 0 ]; then
    cp -a "/home/${existing}/." /home/dev/ 2>/dev/null || true
  fi
  usermod -l dev -d /home/dev -g dev "${existing}"
  if getent group "${existing}" >/dev/null 2>&1 && [ "${existing}" != "dev" ]; then
    groupmod -n dev "${existing}" 2>/dev/null || true
  fi
elif ! getent passwd dev >/dev/null; then
  useradd -m -u "${DEV_UID}" -g dev -s /bin/bash dev
fi

mkdir -p /home/dev
chown -R dev:dev /home/dev
