# Sourced by build-stage network commands (never executed directly).
#
# Corporate trust: when enabled, export the OpenSSL and Node client CA-path
# variables from the constructor-specific PI_CORPORATE_CA_PATH build argument,
# overriding any same-named values inherited from the base image.
#
# Network proxy: when configured, export every required proxy variable from the
# constructor-specific PI_CORPORATE_PROXY_URL / PI_CORPORATE_NO_PROXY build
# arguments, overriding any inherited proxy values.
#
# When either feature is disabled, this script leaves the inherited environment
# untouched.
if [ "${CORPORATE_TRUST_ENABLED:-}" = "true" ]; then
    export SSL_CERT_FILE="${PI_CORPORATE_CA_PATH}"
    export NODE_EXTRA_CA_CERTS="${PI_CORPORATE_CA_PATH}"
fi

if [ -n "${PI_CORPORATE_PROXY_URL:-}" ]; then
    export HTTP_PROXY="${PI_CORPORATE_PROXY_URL}"
    export http_proxy="${PI_CORPORATE_PROXY_URL}"
    export HTTPS_PROXY="${PI_CORPORATE_PROXY_URL}"
    export https_proxy="${PI_CORPORATE_PROXY_URL}"
    export ALL_PROXY="${PI_CORPORATE_PROXY_URL}"
    export all_proxy="${PI_CORPORATE_PROXY_URL}"
fi

if [ -n "${PI_CORPORATE_NO_PROXY:-}" ]; then
    export NO_PROXY="${PI_CORPORATE_NO_PROXY}"
    export no_proxy="${PI_CORPORATE_NO_PROXY}"
fi
