#!/bin/bash
# Build-time Claude bootstrap: privoxy (HTTP) -> SOCKS on host -> claude-bootstrap.sh
set -euo pipefail

HOST_GATEWAY_IP="${HOST_GATEWAY_IP:-}"
SOCKS_PORT="${SOCKS_PORT:?SOCKS_PORT required}"
CLAUDE_TARGET="${CLAUDE_TARGET:-stable}"
PRIVOXY_CONF="/tmp/privoxy-for-build.conf"
PRIVOXY_LOG="/tmp/privoxy.log"
PRIVOXY_PID=""

resolve_gateway() {
    local gateway="${HOST_GATEWAY_IP:-}"
    if [[ -z "${gateway}" || "${gateway}" == "host-gateway" ]]; then
        if [[ -n "${SOCKS_HOST:-}" ]]; then
            gateway="${SOCKS_HOST}"
        elif [[ -n "${EXTERNAL_IP:-}" ]]; then
            gateway="${EXTERNAL_IP}"
        else
            gateway="$(ip route show default | awk '/default/ {print $3; exit}')"
        fi
    fi
    if [[ -z "${gateway}" ]]; then
        echo "Cannot resolve host gateway for SOCKS (set HOST_GATEWAY_IP, SOCKS_HOST, or check network)" >&2
        exit 1
    fi
    printf '%s' "${gateway}"
}

check_socks_reachable() {
    local gateway="$1"
    if command -v nc >/dev/null 2>&1; then
        if ! nc -zv -w 3 "${gateway}" "${SOCKS_PORT}" >/dev/null 2>&1; then
            echo "Cannot reach SOCKS at ${gateway}:${SOCKS_PORT}" >&2
            echo "Ensure SOCKS listens on 0.0.0.0:${SOCKS_PORT} and HOST_GATEWAY_IP/SOCKS_HOST is reachable from the build container." >&2
            exit 1
        fi
    fi
}

stop_privoxy() {
    if [[ -n "${PRIVOXY_PID}" ]]; then
        kill "${PRIVOXY_PID}" 2>/dev/null || true
        wait "${PRIVOXY_PID}" 2>/dev/null || true
        PRIVOXY_PID=""
    fi
}

trap stop_privoxy EXIT

gateway="$(resolve_gateway)"
echo "Bootstrap SOCKS gateway: ${gateway}:${SOCKS_PORT}" >&2
check_socks_reachable "${gateway}"
cat > "${PRIVOXY_CONF}" <<EOF
listen-address  127.0.0.1:8118
forward-socks5   / ${gateway}:${SOCKS_PORT} .
EOF

/usr/sbin/privoxy --no-daemon "${PRIVOXY_CONF}" >"${PRIVOXY_LOG}" 2>&1 &
PRIVOXY_PID=$!
# Wait for privoxy to be ready (poll up to 5 seconds)
for i in $(seq 1 10); do
  if nc -z 127.0.0.1 8118 2>/dev/null; then break; fi
  sleep 0.5
done

export HTTP_PROXY="http://127.0.0.1:8118"
export HTTPS_PROXY="${HTTP_PROXY}"
export ALL_PROXY="${HTTP_PROXY}"

if /usr/local/bin/claude-bootstrap.sh "${CLAUDE_TARGET}"; then
    exit 0
else
    status=$?
    echo "=== privoxy log ==="
    cat "${PRIVOXY_LOG}"
    exit "${status}"
fi
