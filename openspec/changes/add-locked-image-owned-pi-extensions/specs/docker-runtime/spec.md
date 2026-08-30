## MODIFIED Requirements

### Requirement: Expose only image-owned managed extension state at runtime
The project SHALL not derive, mount, or install managed Pi extension artifacts at runtime. A container built from reviewed managed roots and their checked-in lockfile SHALL use the image-owned closure at `/opt/pi-extensions`. Runtime launch SHALL not accept managed-extension overrides, mount a runtime extension projection or artifact blobs, materialize extension artifacts, or expose extension artifact URLs, catalog entries, integrity metadata, or host cache paths to the container.

#### Scenario: Launching an image-owned managed extension closure
- **WHEN** the constructor facade launches an image built with the locked managed extension closure
- **THEN** it SHALL not create or mount a managed-extension runtime projection or artifact blob
- **AND** the container SHALL use the image-owned closure

#### Scenario: Rejecting a managed-extension runtime override
- **WHEN** `run` receives a managed-extension override
- **THEN** it SHALL reject the request before Docker execution
- **AND** SHALL direct the user to edit reviewed roots, run `sync-lock`, review, and rebuild

#### Scenario: Starting without extension installation
- **WHEN** the container starts
- **THEN** startup SHALL not download, install, validate from mounted artifacts, or mutate image-owned managed extensions

### Requirement: Include bundled π skills and extensions
The system SHALL make bundled π assets available in the runtime home directory through constructor-managed runtime setup and SHALL make managed extension roots available from the image-owned locked closure. It SHALL NOT ship the obsolete `/home/dev/install-pi-extensions.sh` compatibility endpoint or a protected runtime managed-extension installer.

#### Scenario: Omitting the legacy extension setup wrapper
- **WHEN** the runtime image is assembled
- **THEN** it SHALL not copy `docker/install-pi-extensions.sh`
- **AND** `/home/dev/install-pi-extensions.sh` SHALL be absent

#### Scenario: Omitting runtime managed-extension setup
- **WHEN** the runtime image is assembled or started
- **THEN** it SHALL not invoke a managed-extension installer against the mounted Pi home
- **AND** `/home/dev/install-pi-extensions.sh` SHALL be absent

#### Scenario: Installing supported extensions after mounting the Pi home
- **WHEN** a container launches with a mounted Pi home
- **THEN** it SHALL not install managed extensions into that home
- **AND** managed roots SHALL remain image-owned

#### Scenario: Registering rtk integration
- **WHEN** runtime setup configures rtk integration
- **THEN** it SHALL not require managed-extension installation
- **AND** repeated launches SHALL not duplicate configuration

#### Scenario: Rejecting an unavailable Pi home
- **WHEN** the expected Pi home is unavailable
- **THEN** runtime setup SHALL fail only for Pi-home-dependent user state
- **AND** SHALL not attempt managed-extension installation in an image path

#### Scenario: Following the supported migration path
- **WHEN** a user needs to change managed extensions
- **THEN** documentation SHALL direct the user to edit roots, run `sync-lock`, review, and rebuild
- **AND** SHALL not present runtime setup as a managed-extension installation path

### Requirement: Expose one constructor CLI facade
The project SHALL expose `docker/docker-constructor.py` as the sole supported user-facing command entry point. The facade SHALL provide primary commands `build`, `run`, `check-deps`, and `sync-lock` and auxiliary commands `validate`, `show`, `doctor`, and `verify`; it SHALL NOT expose a `schema` command. `sync-lock` SHALL orchestrate every registered Constructor-managed lock owner and publish their validated candidates all-or-nothing.

#### Scenario: Delegating a facade command
- **WHEN** a user invokes any supported constructor command with command-specific or global flags
- **THEN** the facade SHALL parse and validate user arguments, coordinate prompts, render output, and map errors to exit codes
- **AND** it SHALL delegate inventory, networking, project selection, provider, Docker orchestration, lock synchronization, and verification behavior to internal APIs

#### Scenario: Verifying through the facade
- **WHEN** a user invokes `docker-constructor.py verify` with selected verification flags
- **THEN** internal verification APIs SHALL execute the requested checks and return structured results
- **AND** the facade SHALL only select checks and present those results

#### Scenario: Avoiding competing entry points
- **WHEN** maintained documentation or repository-owned automation invokes constructor behavior
- **THEN** it SHALL use `docker/docker-constructor.py`
- **AND** it SHALL NOT invoke internal resolver, assembler, standalone verification, Compose, or build-wrapper modules as user-facing commands

#### Scenario: Synchronizing Constructor-managed locks
- **WHEN** a user invokes `docker-constructor.py sync-lock`
- **THEN** the facade SHALL orchestrate all registered lock owners in deterministic order
- **AND** SHALL publish no checked-in lockfile until every candidate is generated and validated
- **AND** SHALL finish with either the complete prior lock set or the complete synchronized lock set

### Requirement: Verify tools against the effective inventory
The runtime image SHALL expose the effective build inventory needed to verify ordinary image-provided tools. Runtime verification SHALL compare those installed tools with their effective values. Managed Pi extensions SHALL NOT be represented in or verified from an effective runtime inventory; they SHALL be verified as the image-owned closure assembled from reviewed exact roots and the checked-in lockfile.

#### Scenario: Verifying configured runtime tools
- **WHEN** the runtime smoke check runs as `dev`
- **THEN** it SHALL verify Node, Rust/Cargo, rustfmt/clippy, uv, Python, ty, Pi, OpenSpec, rtk, and fd against the effective inventory
- **AND** SHALL report actionable version mismatches

#### Scenario: Verifying configured Pi extensions
- **WHEN** runtime verification checks managed Pi extensions
- **THEN** it SHALL verify every reviewed exact root is available at its canonical path beneath `/opt/pi-extensions/node_modules`
- **AND** SHALL verify the installed managed closure corresponds to the build-time evidence and managed-root manifest
- **AND** SHALL NOT invoke an installer, read an effective runtime dependency projection or mounted-artifact metadata, or inspect a managed package in the mounted Pi home

## REMOVED Requirements

### Requirement: Warn about unreachable runtime artifact alternatives
**Reason**: Managed Pi extensions no longer have runtime artifact catalogs, non-default runtime alternatives, or an override policy from which reachability could be computed. Offline `validate` therefore SHALL NOT emit unreachable-catalog-version warnings for managed Pi extensions.

**Migration**: Change an exact reviewed managed root, run `sync-lock`, review and validate the synchronized lockfile set, and rebuild the image. No runtime alternative remains selectable.
