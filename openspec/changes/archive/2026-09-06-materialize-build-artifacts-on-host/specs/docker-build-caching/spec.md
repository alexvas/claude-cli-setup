## ADDED Requirements

### Requirement: Cache locked Pi dependency downloads with the shared assembler
Pi assembly SHALL use the opaque download cache and standalone pinned container supplied by `locked-npm-environment-assembly`. Cache contents SHALL remain outside final image layers, SHALL NOT determine dependency versions independently of the official lockfile, and SHALL be disposable without affecting correctness. BuildKit SHALL perform no Pi npm download or installation.

#### Scenario: Rebuilding Pi with a warm npm cache
- **WHEN** standalone Pi assembly executes with cached tarballs matching the official lockfile
- **THEN** npm SHALL reuse those downloads where valid
- **AND** SHALL install exactly the locked dependency graph

#### Scenario: Building Pi with an empty npm cache
- **WHEN** the shared assembler npm cache is absent or pruned
- **THEN** npm SHALL fetch every required locked dependency before Docker build, verify locked SRI when present, and apply pinned npm's native registry integrity behavior to accepted integrity-less exact HTTPS registry nodes
- **AND** assembler evidence SHALL identify every integrity-less node and canonically hash the published output tree
- **AND** the build SHALL not require Constructor to interpret npm cache internals

### Requirement: Preserve independent artifact-stage invalidation with named inputs
Each logical prebuilt artifact SHALL retain an independent Docker stage and stable named-context filename. Changing one selected artifact or digest SHALL invalidate its consuming stage and dependent assembly while leaving unrelated artifact stages cacheable.

#### Scenario: Changing only the rtk artifact
- **WHEN** only the reviewed rtk bytes or digest change in the named context
- **THEN** the rtk stage and dependent final assembly SHALL rebuild
- **AND** the fd, rustup, uv, Pi, and OpenSpec stages SHALL remain eligible for BuildKit cache reuse
