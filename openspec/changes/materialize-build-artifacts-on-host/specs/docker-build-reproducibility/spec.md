## ADDED Requirements

### Requirement: Construct pinned build inputs without Dockerfile artifact downloads
The canonical build SHALL resolve `linux-amd64` reviewed artifacts before Docker execution and SHALL supply their verified local snapshot to BuildKit. Dockerfile stages for rustup, uv, rtk, and fd SHALL perform no network request for those artifacts. Existing Docker images SHALL be self-contained and SHALL not depend on retained source blobs.

#### Scenario: Building with materialized artifacts
- **WHEN** the canonical image build starts with all selected artifacts verified
- **THEN** Docker SHALL consume them from the dedicated local named context
- **AND** the corresponding stages SHALL not receive or fetch artifact URLs

#### Scenario: Running an existing image after cache cleanup
- **WHEN** source blobs used to build an existing image have been removed from the checkout cache
- **THEN** that image and its containers SHALL remain operational

### Requirement: Own reviewed Node assembler toolchain expectations
The closed `[build.stages.base.node]` inventory SHALL contain required exact non-empty `node_version` and `npm_version` fields alongside the reviewed image tag and digest. These fields SHALL be the sole reviewed expected tool versions supplied to the shared assembler by Pi and later npm consumers; neither value SHALL be inferred from the image tag or lock metadata. Inventory validation SHALL reject missing, malformed, or unknown fields before materialization or Docker execution.

#### Scenario: Supplying reviewed assembler versions
- **WHEN** Pi materialization is planned
- **THEN** the exact reviewed `node_version` and `npm_version` SHALL be supplied to the assembler from `[build.stages.base.node]`
- **AND** no second expected-version source SHALL be derived

### Requirement: Install Pi from its authoritative locked release metadata
The reviewed Pi source SHALL declare npm package `@earendil-works/pi-coding-agent`, release repository `earendil-works/pi`, and release tag prefix `v`. For selected version `<version>`, the authoritative release base URL SHALL be exactly `https://github.com/earendil-works/pi/releases/download/v<version>/`, and the required asset names SHALL be exactly `pi-coding-agent-install-package.json`, `pi-coding-agent-install-package-lock.json`, and `SHA256SUMS`. The build SHALL use the two installation files only after their bytes match their respective entries in that release's `SHA256SUMS`. Before Docker build, Constructor SHALL call the side-effect-free `locked-npm-environment-assembly` input preflight with exact lock bytes, plural reviewed roots, platform, and reviewed Node/npm versions. Preflight SHALL return a digest-bound validated input with root metadata keyed by package identity/path only after requiring `[build.stages.base.node].node_version` to satisfy every reviewed-root `engines.node`; incompatibility of any root SHALL identify that root and fail with no Docker, npm, network, cache, staging, lock, publication, output path, or output evidence. Syntax-valid transitive `engines.node` metadata SHALL be accepted and discarded without enabling `engine-strict` or constraining the reviewed Node version. Constructor SHALL select exact reviewed root `@earendil-works/pi-coding-agent` and its resolved lock path and consume `bin.pi` only from that preflight result, never from another root or reparsed raw metadata. It SHALL then pass the same validated input and exact lock bytes to Docker-backed assembly, which SHALL recheck all bindings before effects, assert actual Node/npm versions, run `npm ci`, and return the validated Pi tree and output evidence. The consumer, not the assembler, SHALL construct `/opt/pi/bin/pi`; its selected target SHALL be a non-empty safe relative path whose complete filesystem resolution, including every symlink, is non-dangling and contained within the assembled Pi environment. Constructor SHALL produce consumer evidence recording the launcher’s exact contents, non-writable executable mode, resolved target, and containment within the Pi environment. A post-materialization transaction/build-plan attestation SHALL supply the expected assembler environment identity and deterministic consumer-launcher-evidence digest as BuildKit inputs. The complete immutable tree, assembler evidence, and consumer launcher evidence SHALL enter the named build context; BuildKit SHALL match both evidence identities to those expected attestation values before verifying their contents and before copy, and runtime/final-layout verification SHALL verify the installed launcher and evidence again in the final image. Resolved build projection and dry-run rendering SHALL remain side-effect free and SHALL carry only the closed `prospective` attestation state rather than output-derived identities. BuildKit SHALL perform no Pi npm networking or installation, and the installed command and SDK layout under `/opt/pi` SHALL preserve the existing container interface.

#### Scenario: Deriving authoritative Pi release URLs
- **WHEN** reviewed Pi version `0.84.3`, repository `earendil-works/pi`, and tag prefix `v` are selected
- **THEN** the constructor SHALL request `https://github.com/earendil-works/pi/releases/download/v0.84.3/SHA256SUMS`
- **AND** SHALL request the two exact installation asset names beneath the same release base URL

#### Scenario: Installing a valid Pi release
- **WHEN** the selected authoritative Pi release publishes matching installation package, lockfile, and SHA256SUMS entries
- **THEN** the build SHALL verify the two files and run lockfile-frozen installation with scripts disabled
- **AND** the final image SHALL expose the selected Pi through the established command and module paths

#### Scenario: Rejecting invalid consumer launcher evidence
- **WHEN** the derived launcher’s target is unsafe or escapes the Pi environment, its contents or mode differ from consumer evidence, or its consumer evidence or assembler environment identity differs from the expected post-materialization attestation value
- **THEN** snapshot admission or final-layout copy SHALL fail
- **AND** the launcher and Pi environment SHALL NOT enter the final image

#### Scenario: Rejecting incomplete Pi installation metadata
- **WHEN** the release repository or tag prefix is absent or invalid, any required asset is absent, either installation checksum is absent, or installation bytes do not match SHA256SUMS
- **THEN** host materialization SHALL fail before snapshot publication, npm installation, or Docker execution

#### Scenario: Preserving npm integrity checks
- **WHEN** npm fetches a dependency selected by the official lockfile
- **THEN** it SHALL verify the package against that lockfile entry's integrity
- **AND** an integrity mismatch SHALL fail the build
