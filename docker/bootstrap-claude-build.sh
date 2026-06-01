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
    local gateway="${HOST_GATEWAY_IP}"
    if [[ -z "${gateway}" || "${gateway}" == "host-gateway" ]]; then
        gateway="$(ip route show default | awk '/default/ {print $3; exit}')"
    fi
    if [[ -z "${gateway}" ]]; then
        echo "Cannot resolve host gateway for SOCKS (set HOST_GATEWAY_IP or check network)" >&2
        exit 1
    fi
    printf '%s' "${gateway}"
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
cat > "${PRIVOXY_CONF}" <<EOF
listen-address  127.0.0.1:8118
forward-socks5   / ${gateway}:${SOCKS_PORT} .
EOF

/usr/sbin/privoxy --no-daemon "${PRIVOXY_CONF}" >"${PRIVOXY_LOG}" 2>&1 &
PRIVOXY_PID=$!
sleep 1

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
