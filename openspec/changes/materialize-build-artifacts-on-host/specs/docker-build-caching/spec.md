## ADDED Requirements

### Requirement: Cache locked Pi dependency downloads with BuildKit
The Pi installation stage SHALL use a Pi-specific BuildKit npm cache mount while running `npm ci`. Cache contents SHALL remain outside final image layers, SHALL NOT determine dependency versions independently of the official lockfile, and SHALL be disposable without affecting correctness.

#### Scenario: Rebuilding Pi with a warm npm cache
- **WHEN** the Pi installation stage executes with cached tarballs matching the official lockfile
- **THEN** npm SHALL reuse those downloads where valid
- **AND** SHALL install exactly the locked dependency graph

#### Scenario: Building Pi with an empty npm cache
- **WHEN** the Pi-specific BuildKit cache is absent or pruned
- **THEN** npm SHALL fetch and integrity-check every required locked dependency
- **AND** the build SHALL not require a constructor-managed npm cache format

### Requirement: Preserve independent artifact-stage invalidation with named inputs
Each logical prebuilt artifact SHALL retain an independent Docker stage and stable named-context filename. Changing one selected artifact or digest SHALL invalidate its consuming stage and dependent assembly while leaving unrelated artifact stages cacheable.

#### Scenario: Changing only the rtk artifact
- **WHEN** only the reviewed rtk bytes or digest change in the named context
- **THEN** the rtk stage and dependent final assembly SHALL rebuild
- **AND** the fd, rustup, uv, Pi, and OpenSpec stages SHALL remain eligible for BuildKit cache reuse
