#!/usr/bin/env sh
# Strict dependency-free PEM validation for the fixed corporate trust bundle.
#
# Mirrors the host-side validator contract (docker/versioning/inventory.py):
# ASCII input, complete standalone ``-----BEGIN CERTIFICATE-----`` /
# ``-----END CERTIFICATE-----`` delimiters, no non-whitespace content outside
# those blocks, and strictly decodable nonempty Base64 payloads.  X.509
# semantics (validity, signatures, trust chains, coverage) remain the
# operator's responsibility.
#
# Usage: validate-corporate-bundle.sh <bundle-path>
# Exits 0 when valid, 1 with a diagnostic on stderr otherwise.

set -eu

bundle="${1:?usage: validate-corporate-bundle.sh <bundle-path>}"
fail() {
    printf 'corporate trust bundle %s: %s\n' "$bundle" "$1" >&2
    exit 1
}

[ -f "$bundle" ] || fail "missing"
[ -s "$bundle" ] || fail "empty"

# ASCII text only: printable ASCII plus tab are permitted.  CR/LF are removed
# here only so line breaks do not trip the check; bare or embedded CR
# placement is validated by the framing pass below.  Non-ASCII bytes and
# control characters (other than tab) are rejected outright.
if LC_ALL=C tr -d '\r\n' < "$bundle" | LC_ALL=C grep -q '[^[:print:][:blank:]]'; then
    fail "non-ASCII or control content"
fi

# Framing + per-block Base64 shape.  Only a CR immediately preceding LF (a
# CRLF line boundary) is normalized to LF; any bare or embedded CR remains in
# its line and is rejected by the boundary/payload checks below, matching the
# host-side LF/CRLF-only line-boundary rule.  Distinct exit codes are mapped
# below.
set +e
awk '
    BEGIN {
        begin = "-----BEGIN CERTIFICATE-----"
        end = "-----END CERTIFICATE-----"
        in_block = 0
        blocks = 0
        payload = ""
        status = 0
    }
    {
        line = $0
        sub(/\r$/, "", line)
        stripped = line
        sub(/^[ \t]+/, "", stripped)
        sub(/[ \t]+$/, "", stripped)
        if (stripped == begin) {
            if (in_block) { status = 2; exit }
            in_block = 1
            blocks++
            payload = ""
            next
        }
        if (stripped == end) {
            if (!in_block) { status = 3; exit }
            if (payload !~ /^[A-Za-z0-9+/]+={0,2}$/ || length(payload) % 4 != 0) { status = 8; exit }
            in_block = 0
            next
        }
        if (in_block) {
            if (index(stripped, begin) || index(stripped, end)) { status = 2; exit }
            payload = payload line
        } else {
            if (stripped != "") { status = 5; exit }
        }
    }
    END {
        if (status != 0) exit status
        if (in_block) exit 6
        if (blocks == 0) exit 7
        exit 0
    }
' "$bundle"
code=$?
set -e
case "$code" in
    0) ;;
    2) fail "nested or misordered PEM certificate delimiters" ;;
    3) fail "unmatched PEM certificate delimiters" ;;
    5) fail "non-PEM content outside certificate blocks" ;;
    6) fail "unterminated PEM certificate block" ;;
    7) fail "no PEM certificate blocks" ;;
    8) fail "invalid Base64 payload" ;;
    *) fail "invalid PEM framing" ;;
esac
