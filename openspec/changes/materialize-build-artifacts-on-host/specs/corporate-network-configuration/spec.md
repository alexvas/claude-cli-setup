## ADDED Requirements

### Requirement: Apply corporate network policy to host artifact materialization
When corporate trust or a credential-free proxy is enabled, host-side build artifact requests SHALL use the validated local proxy and replacement trust bundle under the same confidentiality and redaction rules as build networking. When disabled, host requests SHALL retain standard host trust and proxy behavior without constructor-defined certificate overrides. Invalid enabled configuration SHALL prevent downloads and Docker execution.

#### Scenario: Downloading through enabled corporate configuration
- **WHEN** a selected build artifact is absent and valid corporate trust or proxy settings are enabled
- **THEN** host materialization SHALL apply those settings to the artifact request
- **AND** diagnostics SHALL not reveal proxy credentials or sensitive endpoint components

#### Scenario: Materializing with corporate configuration disabled
- **WHEN** corporate trust and constructor proxy settings are disabled
- **THEN** host materialization SHALL introduce no constructor-defined CA path or proxy override

#### Scenario: Rejecting invalid corporate configuration before download
- **WHEN** enabled corporate settings fail their existing validation
- **THEN** the build SHALL fail before host artifact network access, snapshot publication, or Docker execution
