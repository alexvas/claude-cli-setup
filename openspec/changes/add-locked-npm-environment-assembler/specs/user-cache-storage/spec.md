## ADDED Requirements

### Requirement: Store opaque npm downloads and assembled environments privately
The resolved constructor cache SHALL provide an owner-private assembler namespace keyed by assembler identity. It SHALL keep npm's download cache opaque and disposable and never treat it as authority. It SHALL store immutable published environments only by `AssembledOutputIdentity`, derived from assembler input identity, canonical output-tree digest, and canonical assembler-evidence digest, with private locks, staging, manifests, and evidence. Storage keyed only by assembler input identity SHALL NOT be described as content-addressed and SHALL NOT hold an authoritative assembled output. A non-authoritative input-identity index MAY reference zero, one, or multiple output identities and SHALL never permit distinct outputs to overwrite or alias one another. Pi and extension consumers MAY reuse downloads while retaining independent output identities and lifecycle policies.

#### Scenario: Reusing an npm download
- **WHEN** independent assemblies need a tarball already present in the assembler cache
- **THEN** npm MAY reuse its opaque cache entry subject to locked SRI verification when present and pinned npm's native registry integrity behavior when the accepted lock entry omits SRI
- **AND** published environment reuse SHALL require complete canonical tree-evidence verification and recomputation of the selected output identity, tree digest, and evidence digest
- **AND** removing the cache SHALL affect performance only

#### Scenario: Separating consumer environments
- **WHEN** Pi and extension assemblies share downloaded package bytes
- **THEN** their published trees, evidence, retention, and committed identities SHALL remain independent

### Requirement: Secure assembler cache ownership and cleanup
Assembler cache roots, locks, staging, and mutable npm state SHALL be owner-only; published trees SHALL be non-writable and no-follow validated. Foreign ownership, symlinked control paths, unsafe entry types, cancellation residue, and publication outside the resolved cache root SHALL be rejected or cleaned before reuse without chmod of pre-existing ancestors.

#### Scenario: Rejecting unsafe assembler storage
- **WHEN** an assembler cache or staging path is symlinked, foreign-owned, non-directory, or escapes the resolved root
- **THEN** assembly SHALL fail before container execution or publication with actionable recovery guidance
