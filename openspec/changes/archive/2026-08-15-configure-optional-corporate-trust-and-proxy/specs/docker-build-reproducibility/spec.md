## ADDED Requirements

### Requirement: Apply optional local corporate network inputs to construction
The canonical build command SHALL accept validated optional local corporate trust and proxy inputs without adding their values to the reviewed dependency inventory or effective dependency projection. When disabled, construction SHALL preserve its existing Docker argument vector and trust behavior. When enabled, the build vector SHALL provide the fixed local trust-bundle build-context convention and the required named proxy build arguments deterministically.

#### Scenario: Default construction has no corporate network inputs
- **WHEN** no corporate trust or proxy settings are configured locally
- **THEN** the rendered build vector SHALL contain no corporate proxy build arguments
- **AND** construction SHALL not require a local bundle file

#### Scenario: Enabled construction uses local-only inputs
- **WHEN** valid corporate trust and/or proxy settings are configured in the resolved local companion
- **THEN** build planning SHALL use those settings without serializing their endpoint or certificate contents into `docker-constructor.toml` or the effective dependency projection
- **AND** invalid inputs SHALL prevent Docker build execution
