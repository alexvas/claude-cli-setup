## Why

The protected runtime installer is now invoked directly by the container entrypoint, leaving `/home/dev/install-pi-extensions.sh` as a compatibility wrapper that duplicates no behavior but remains copied into every image. Removing that obsolete endpoint simplifies the runtime surface and prevents documentation, verification, and tests from preserving a legacy manual workflow.

## What Changes

- **BREAKING** Remove the supported `/home/dev/install-pi-extensions.sh` compatibility endpoint from runtime images.
- Remove `docker/install-pi-extensions.sh` and its Dockerfile copy/permission setup.
- Make automatic entrypoint invocation of `docker.runtime_installer` the only runtime extension-installation path.
- Replace manual wrapper instructions and verification with the constructor-managed run workflow and direct internal module checks where appropriate.
- Update runtime verification, evidence generation, semantic-source checks, and documentation so they no longer require or invoke the removed script.
- Remove stale comments and diagrams that identify the shell wrapper as the extension installer.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `docker-runtime`: Remove the requirement to ship a protected shell setup script and require constructor-launched entrypoint installation through the protected internal runtime installer instead.

## Impact

- Runtime image contents and the previously documented `/home/dev/install-pi-extensions.sh` path.
- `Dockerfile`, `docker/install-pi-extensions.sh`, entrypoint/runtime verification, Stage 6 evidence, and source-contract tests.
- README variants and OpenSpec diagrams or prose that still name the wrapper.
- External callers of the image-local script must migrate to `docker/docker-constructor.py run`; direct internal module invocation remains an implementation/debug mechanism rather than a public constructor command.
