## ADDED Requirements

### Requirement: Store opaque npm downloads and assembled environments privately
The resolved constructor cache SHALL provide an owner-private assembler namespace keyed by assembler identity. It SHALL keep npm's download cache opaque and disposable, never treat it as authority, and store published assembled environments by deterministic environment identity with private locks, staging, manifests, and evidence. Pi and extension consumers MAY reuse downloads while retaining independent environment identities and lifecycle policies.

#### Scenario: Reusing an npm download
- **WHEN** independent assemblies need a tarball already present in the assembler cache
- **THEN** npm MAY reuse its opaque cache entry subject to lockfile integrity verification
- **AND** removing the cache SHALL affect performance only

#### Scenario: Separating consumer environments
- **WHEN** Pi and extension assemblies share downloaded package bytes
- **THEN** their published trees, evidence, retention, and committed identities SHALL remain independent

### Requirement: Secure assembler cache ownership and cleanup
Assembler cache roots, locks, staging, and mutable npm state SHALL be owner-only; published trees SHALL be non-writable and no-follow validated. Foreign ownership, symlinked control paths, unsafe entry types, cancellation residue, and publication outside the resolved cache root SHALL be rejected or cleaned before reuse without chmod of pre-existing ancestors.

#### Scenario: Rejecting unsafe assembler storage
- **WHEN** an assembler cache or staging path is symlinked, foreign-owned, non-directory, or escapes the resolved root
- **THEN** assembly SHALL fail before container execution or publication with actionable recovery guidance
