## MODIFIED Requirements

### Requirement: Configure optional local corporate trust
The system SHALL support an optional `[corporate-trust]` section only in `docker-constructor.local.toml` beneath the selected constructor project directory. `enabled` SHALL be a boolean; absent or `false` SHALL disable corporate trust. When `enabled = true`, the system SHALL require the sole trust source to be `<project-directory>/.docker-local/corporate-ca-bundle.crt`, validate that it is readable and contains one or more nonempty PEM `CERTIFICATE` blocks, and reject missing, unreadable, malformed, or unknown local configuration before Docker execution. The trust path SHALL never be derived from the constructor installation directory. PEM validation SHALL be dependency-free and SHALL require ASCII input, matching complete `BEGIN CERTIFICATE`/`END CERTIFICATE` delimiters, no non-whitespace content outside those blocks, and strictly decodable nonempty Base64 payloads. It SHALL not parse, verify, or assess payloads as X.509 certificates; certificate validity, trust-chain validity, and organizational trust coverage remain the operator's responsibility. The supplied file SHALL be treated as a complete replacement trust bundle.

#### Scenario: Corporate trust is disabled by default
- **WHEN** the selected project's local companion is absent or omits `[corporate-trust]`
- **THEN** build and run SHALL retain the standard image trust store
- **AND** SHALL not require `.docker-local/corporate-ca-bundle.crt`

#### Scenario: Enabled corporate trust has a valid fixed bundle
- **WHEN** the selected project's local companion declares `[corporate-trust] enabled = true` and its fixed bundle is valid
- **THEN** build and run planning SHALL use that exact project-owned file as the only corporate trust source
- **AND** SHALL not read an arbitrary certificate path from configuration or the tool installation

#### Scenario: Enabled corporate trust has no usable bundle
- **WHEN** corporate trust is enabled and the selected project's fixed bundle is missing, unreadable, empty, has incomplete or unmatched certificate delimiters, contains non-whitespace text outside certificate blocks, or has an empty or non-Base64-decodable block payload
- **THEN** the invoking command SHALL fail with a path-specific CONFIG error before Docker execution

#### Scenario: Certificate semantics remain an operator responsibility
- **WHEN** an enabled fixed bundle has complete PEM `CERTIFICATE` blocks with nonempty, strictly decodable Base64 payloads
- **THEN** the invoking command SHALL accept the bundle without an X.509 parser or external Python dependency
- **AND** any invalid certificate object, expired certificate, invalid signature, missing trust root, or incomplete corporate coverage SHALL remain an operator responsibility
