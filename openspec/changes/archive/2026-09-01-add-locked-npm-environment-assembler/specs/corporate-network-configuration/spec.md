## ADDED Requirements

### Requirement: Apply resolved credential-free network policy to npm assembler containers
Standalone npm assembler containers SHALL receive the same resolved credential-free proxy and enabled corporate trust inputs as host-orchestrated dependency acquisition, scoped only to the assembly process. Enabled trust SHALL be mounted read-only at the fixed system trust path before npm network access; disabled trust SHALL introduce no override. The assembler SHALL NOT persist configured proxy endpoints or trust paths in command displays, logs, evidence, output trees, or cache manifests.

#### Scenario: Assembling behind an enabled corporate network
- **WHEN** corporate trust and a credential-free proxy are enabled and valid
- **THEN** the assembler SHALL use those resolved inputs for locked HTTPS registry requests
- **AND** the assembled output and evidence SHALL contain neither the configured proxy endpoint nor trust path

#### Scenario: Preserving default assembler trust
- **WHEN** corporate trust and proxy configuration are disabled
- **THEN** assembler execution SHALL preserve the pinned image's default trust and introduce no constructor-defined certificate or proxy setting
