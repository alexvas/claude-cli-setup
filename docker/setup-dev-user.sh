#!/bin/bash
# Ensure user "dev" exists with DEV_UID (Ubuntu images often have UID 1000 as "ubuntu").
set -euo pipefail

DEV_UID="${DEV_UID:-1000}"

if id dev >/dev/null 2>&1; then
  chown -R dev:dev /home/dev 2>/dev/null || true
  exit 0
fi

if existing="$(getent passwd "${DEV_UID}" | cut -d: -f1)" && [ -n "${existing}" ] && [ "${existing}" != "dev" ]; then
  mkdir -p /home/dev
  if [ -d "/home/${existing}" ] && [ "$(ls -A "/home/${existing}" 2>/dev/null | wc -l)" -gt 0 ]; then
    cp -a "/home/${existing}/." /home/dev/ 2>/dev/null || true
  fi
  usermod -l dev -d /home/dev "${existing}"
  if getent group "${existing}" >/dev/null 2>&1; then
    groupmod -n dev "${existing}" 2>/dev/null || true
  fi
elif ! getent passwd dev >/dev/null; then
  useradd -m -u "${DEV_UID}" -s /bin/bash dev
fi

mkdir -p /home/dev
chown -R dev:dev /home/dev
