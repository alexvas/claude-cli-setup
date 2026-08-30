## MODIFIED Requirements

### Requirement: Store persistent constructor caches under a private XDG root
The constructor SHALL use `${XDG_CACHE_HOME}/docker-constructor` as its default persistent cache root when `XDG_CACHE_HOME` is non-empty and absolute, and `~/.cache/docker-constructor` only when it is empty or non-absolute. It SHALL store HTTP update-discovery data only in the `versioning` child and assembler-owned opaque npm downloads and published assembled environments in their dedicated assembler namespace. Managed image-owned Pi extensions SHALL NOT use `runtime-artifacts/blobs`, runtime projections, or per-launch artifact cache state.

#### Scenario: Preparing managed extension assembly storage
- **WHEN** a build assembles managed Pi extensions
- **THEN** it SHALL use the assembler-owned opaque download cache and published environment storage
- **AND** it SHALL not create managed-extension runtime artifact blobs or projections

#### Scenario: Using a valid existing XDG cache home
- **WHEN** an existing valid XDG cache home is used
- **THEN** assembler storage SHALL remain private beneath the constructor cache root
- **AND** managed extensions SHALL not use `runtime-artifacts/blobs`

#### Scenario: Creating a missing explicit XDG cache home
- **WHEN** an explicit XDG cache home is missing
- **THEN** the constructor SHALL create it with owner-only permissions before assembler storage

#### Scenario: Falling back from an absent or relative XDG cache home
- **WHEN** XDG cache home is absent or relative
- **THEN** the constructor SHALL use its normal private fallback root for assembler storage

#### Scenario: Rejecting an unusable explicit XDG cache home
- **WHEN** an explicit XDG cache home is unusable
- **THEN** assembly SHALL fail before cache mutation or Docker execution

#### Scenario: Keeping generated output in the checkout
- **WHEN** a build creates a generated named-context snapshot or evidence output
- **THEN** it SHALL retain the repository-local generated-output location
- **AND** SHALL not treat it as persistent runtime extension cache state

#### Scenario: Launching a managed extension image
- **WHEN** a container launches with image-owned managed extensions
- **THEN** launch SHALL not read, create, or clean a managed-extension runtime artifact cache
