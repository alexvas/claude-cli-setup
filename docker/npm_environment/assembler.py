"""Fixed npm policy and the consumer-neutral assembler script.

The assembler runs one canonical shell script inside the reviewed Node image.
The script first asserts the container's actual Node and npm versions equal
the caller-reviewed values, then synthesizes a project manifest in sync with
the mounted lockfile, and finally runs exactly
``npm ci --ignore-scripts --no-bin-links --no-audit --no-fund``.  Lifecycle
scripts never run, ``engine-strict`` stays disabled, and no reviewed-root
``bin`` metadata creates an executable link.

The script bytes and the npm policy flags are canonical constants so callers
derive ``script_digest``/``policy_digest`` for :class:`AssemblerIdentity`
from these exact bytes rather than from any ambient or consumer input.
"""

from __future__ import annotations

import hashlib
import json

#: The one fixed npm invocation policy.  ``--ignore-scripts`` disables all
#: lifecycle scripts, ``--no-bin-links`` prevents executable-link creation,
#: and ``--no-audit``/``--no-fund`` disable network advisory/funding probes.
NPM_CI_FLAGS = ("--ignore-scripts", "--no-bin-links", "--no-audit", "--no-fund")

NPM_CI_COMMAND = ("npm", "ci") + NPM_CI_FLAGS

#: Structured assembler-script exit codes.
EXIT_NODE_VERSION_MISMATCH = 65
EXIT_NPM_VERSION_MISMATCH = 66

#: Root dependency-declaration maps the assembler copies into the
#: synthesized project manifest.  These are exactly the dependency classes
#: lockfile closure validation treats as *installed* root edges.
#: ``peerDependencies`` is deliberately absent: validation leaves root peers
#: to the consumer environment rather than installing them, so copying them
#: into the manifest would make ``npm ci`` install an unvalidated package.
MANIFEST_DEPENDENCY_KEYS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
)

#: Canonical consumer-neutral assembler script (fixed bytes).
ASSEMBLER_SCRIPT = """\
#!/bin/sh
set -eu

mkdir -p /cache/home

node_actual="$(node --version)"
if [ "${node_actual}" != "v${REVIEWED_NODE_VERSION}" ]; then
    printf 'node version mismatch: got %s, want v%s\\n' "${node_actual}" "${REVIEWED_NODE_VERSION}" >&2
    exit 65
fi

npm_actual="$(npm --version)"
if [ "${npm_actual}" != "${REVIEWED_NPM_VERSION}" ]; then
    printf 'npm version mismatch: got %s, want %s\\n' "${npm_actual}" "${REVIEWED_NPM_VERSION}" >&2
    exit 66
fi

cd /work

node -e 'const fs=require("fs");const lock=JSON.parse(fs.readFileSync("/work/package-lock.json","utf8"));const r=lock.packages[""];const pkg={name:r.name||"npm-assembler",version:r.version||"0.0.0",private:true};for(const k of ["dependencies","devDependencies","optionalDependencies"]){if(r[k]&&typeof r[k]==="object")pkg[k]=r[k];}fs.writeFileSync("/work/package.json",JSON.stringify(pkg,null,2)+"\\n");'

exec npm ci --ignore-scripts --no-bin-links --no-audit --no-fund
"""


def assembler_script_bytes() -> bytes:
    """Return the exact UTF-8 bytes of the canonical assembler script."""
    return ASSEMBLER_SCRIPT.encode("utf-8")


def assembler_script_digest() -> str:
    """Return the SHA-256 hex digest of the canonical assembler script."""
    return hashlib.sha256(assembler_script_bytes()).hexdigest()


def npm_policy_flags() -> tuple[str, ...]:
    """Return the one fixed npm invocation policy flag tuple."""
    return NPM_CI_FLAGS


def npm_policy_digest() -> str:
    """Return the SHA-256 hex digest of the canonical npm policy flags."""
    payload = json.dumps(
        list(NPM_CI_FLAGS), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
