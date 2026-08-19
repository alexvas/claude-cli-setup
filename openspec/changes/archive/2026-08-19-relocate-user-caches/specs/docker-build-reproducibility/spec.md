## MODIFIED Requirements

### Requirement: Keep cache directory paths machine-local
The reviewed `docker-constructor.toml` SHALL NOT accept `cache.dir`; a custom dedicated constructor cache root SHALL be read only from an absolute `[cache].dir` in the resolved local TOML companion. When it is absent, cache consumers SHALL use `${XDG_CACHE_HOME}/docker-constructor` when `XDG_CACHE_HOME` is non-empty and absolute, creating a missing XDG directory with `0700` or requiring an existing writable directory; they SHALL use `~/.cache/docker-constructor` only when XDG is empty or non-absolute, and SHALL reject an explicit absolute non-directory or unwritable XDG path without fallback. Cache consumers SHALL derive their separate named subdirectories beneath the resolved root rather than storing unrelated cache formats in one directory. Reviewed `cache.ttl` SHALL remain supported in `docker-constructor.toml` as portable HTTP cache policy.

#### Scenario: Migrating a reviewed cache directory
- **WHEN** validation encounters `cache.dir` in `docker-constructor.toml`
- **THEN** it SHALL reject the retired field with an instruction to move the value to the corresponding local companion
- **AND** SHALL NOT silently copy, merge, or prefer the reviewed path

#### Scenario: Resolving cache settings from separate sources
- **WHEN** reviewed `cache.ttl` and local `[cache].dir` are both configured
- **THEN** cache consumers SHALL use the reviewed TTL and local cache root together
- **AND** neither value SHALL enter an effective build or runtime projection

#### Scenario: Separating cache formats under a local root
- **WHEN** a local `[cache].dir` is configured
- **THEN** update-discovery HTTP cache data SHALL use its `versioning` child
- **AND** verified runtime artifacts SHALL use its `runtime-artifacts/blobs` child

#### Scenario: Rejecting the removed HTTP-only command-line cache directory
- **WHEN** a user supplies unsupported `check-updates --cache-dir`
- **THEN** command-line parsing SHALL reject the supplied option as unsupported
- **AND** SHALL NOT interpret it, select a cache path, or migrate cache data

## ADDED Requirements

### Requirement: Keep cache TTL in reviewed policy
HTTP cache TTL SHALL be configured only through `[cache].ttl` in the reviewed `docker-constructor.toml`. The command SHALL NOT accept a command-local TTL override. `--no-cache` SHALL remain available as a one-invocation cache bypass and SHALL NOT modify reviewed TTL policy.

#### Scenario: Using reviewed cache TTL
- **WHEN** reviewed `[cache].ttl` is configured
- **THEN** update discovery SHALL apply that TTL to HTTP cache reads and writes
- **AND** SHALL NOT require local cache configuration

#### Scenario: Rejecting the retired TTL option
- **WHEN** a user supplies `check-updates --cache-ttl`
- **THEN** command-line parsing SHALL reject the unsupported option
- **AND** SHALL NOT override reviewed `[cache].ttl`
- **AND** SHALL perform no update discovery or cache mutation

#### Scenario: Bypassing cache for one invocation
- **WHEN** a user supplies `check-updates --no-cache`
- **THEN** update discovery SHALL bypass HTTP cache reads and writes
- **AND** SHALL NOT modify or override reviewed `[cache].ttl`
